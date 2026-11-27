#!/usr/bin/env python3
"""
avaliar_limiar.py
-----------------
Mede, com números, quão bom é o reconhecimento (MB-LBP + distância) e ajuda a
escolher o limiar com critério (curvas FAR/FRR), em vez de ajustar "no olho".

Uso:
    python3 avaliar_limiar.py                       # só leave-one-out em imagens_processadas/
    python3 avaliar_limiar.py --teste fotos_teste   # + fotos de teste de OUTRA sessão

Convenção de nomes (a mesma do cadastro): nome_1.jpg, nome_2.png ...
Na pasta --teste, pessoas que NÃO estão no banco funcionam como impostores
(é o caso "desconhecido tentando entrar").

IMPORTANTE: o leave-one-out usa as próprias fotos de cadastro (tiradas na mesma
sessão) e por isso é otimista. O número que vale é o da pasta --teste, com fotos
de outro dia / outra luz / com e sem barba, etc.
"""
import argparse
import glob
import os
import re
from collections import Counter

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

W = H = 64
B = 3            # tamanho do bloco do MB-LBP
GRID = 5
DX = [0, 1, 2, 2, 2, 1, 0, 0]
DY = [0, 0, 0, 1, 2, 2, 2, 1]


# ----------------------------------------------------------------------------
# Leitura
# ----------------------------------------------------------------------------
def extrair_nome(caminho):
    nome = os.path.splitext(os.path.basename(caminho))[0]
    nome = re.sub(r"_\d+$", "", nome)
    nome = re.split(r"_202", nome)[0]
    return re.sub(r"\d+", "", nome).lower()


def carregar(pasta):
    arqs = []
    for ext in ("jpg", "jpeg", "png", "bmp"):
        arqs += glob.glob(os.path.join(pasta, f"*.{ext}"))
    imgs, nomes = [], []
    for a in sorted(arqs):
        im = cv2.imread(a, cv2.IMREAD_GRAYSCALE)
        if im is None:
            continue
        imgs.append(cv2.resize(im, (W, H)))
        nomes.append(extrair_nome(a))
    return imgs, nomes


# ----------------------------------------------------------------------------
# MB-LBP vetorizado (equivalente bit a bit ao loop do firmware / cadastrar_pessoa)
# ----------------------------------------------------------------------------
def codigos_mblbp(img):
    """Imagem 64x64 de códigos; borda de 4 px fica 0, como no firmware."""
    ii = cv2.integral(img).astype(np.int64)
    n = H - 3 * B + 1  # 56 posições válidas

    def soma(ox, oy):
        return (ii[oy + B:oy + B + n, ox + B:ox + B + n] - ii[oy:oy + n, ox + B:ox + B + n]
                - ii[oy + B:oy + B + n, ox:ox + n] + ii[oy:oy + n, ox:ox + n])

    centro = soma(B, B)
    cod = np.zeros((n, n), dtype=np.uint8)
    for i in range(8):
        cod |= ((soma(DX[i] * B, DY[i] * B) >= centro).astype(np.uint8) << i)
    out = np.zeros((H, W), dtype=np.uint8)
    off = (3 * B) // 2
    out[off:off + n, off:off + n] = cod
    return out


def _tabela_uniforme():
    def trans(c):
        b = [(c >> i) & 1 for i in range(8)]
        return sum(b[i] != b[(i + 1) % 8] for i in range(8))
    tab, k = np.full(256, 58, dtype=np.int64), 0
    for c in range(256):
        if trans(c) <= 2:
            tab[c] = k
            k += 1
    return tab  # 58 padrões uniformes + 1 bin para o resto = 59


TAB59 = _tabela_uniforme()


def bordas(n, g, estilo):
    if estilo == "firmware":       # 0,12,24,36,48,64 -> última célula maior (16 px)
        t = n // g
        return [i * t for i in range(g)] + [n]
    return [round(i * n / g) for i in range(g + 1)]   # células de tamanho ~igual


def feature(cod, cfg):
    if cfg["area"] == "valida":        # descarta a moldura de zeros (4 px)
        cod = cod[4:60, 4:60]
    nb = 256
    if cfg["bins"] == 59:
        cod, nb = TAB59[cod], 59
    ys = bordas(cod.shape[0], GRID, cfg["cel"])
    xs = bordas(cod.shape[1], GRID, cfg["cel"])
    partes = []
    for gy in range(GRID):
        for gx in range(GRID):
            cel = cod[ys[gy]:ys[gy + 1], xs[gx]:xs[gx + 1]]
            h = np.bincount(cel.ravel(), minlength=nb).astype(np.float64)
            if cfg["norm"]:
                h /= h.sum()
            if cfg.get("sqrt"):
                h = np.sqrt(h)
            partes.append(h)
    return np.concatenate(partes)


VARIANTES = {
    "A atual (256 bins, contagem, euclid)":
        dict(area="completa", bins=256, norm=False, cel="firmware", dist="euclid"),
    "B 256 bins, L1 por celula, chi2":
        dict(area="completa", bins=256, norm=True, cel="firmware", dist="chi2"),
    "C uniforme 59, L1, chi2":
        dict(area="completa", bins=59, norm=True, cel="firmware", dist="chi2"),
    "D uniforme 59, L1, chi2, area valida, celulas iguais":
        dict(area="valida", bins=59, norm=True, cel="iguais", dist="chi2"),
    "E idem D com raiz (Hellinger), euclid":
        dict(area="valida", bins=59, norm=True, sqrt=True, cel="iguais", dist="euclid"),
}


# ----------------------------------------------------------------------------
# Distâncias e classificação
# ----------------------------------------------------------------------------
def dist_vec(p, G, metrica):
    if metrica == "euclid":
        return np.sqrt(((G - p) ** 2).sum(1))
    return (((G - p) ** 2) / (G + p + 1e-9)).sum(1)   # chi-quadrado


def dist_classes(Fg, yg, nC, Fp, loo, clf, metrica):
    """Distância de cada probe a cada pessoa. No modo loo, o probe é retirado da própria classe."""
    D = np.full((len(Fp), nC), np.inf)
    cont = np.bincount(yg, minlength=nC)
    idx = [np.where(yg == c)[0] for c in range(nC)]
    if clf == "centroide":
        S = np.zeros((nC, Fg.shape[1]))
        np.add.at(S, yg, Fg)
        C = S / cont[:, None]
        for k in range(len(Fp)):
            D[k] = dist_vec(Fp[k], C, metrica)
            if loo:
                c = yg[k]
                if cont[c] >= 2:
                    D[k, c] = dist_vec(Fp[k], ((S[c] - Fg[k]) / (cont[c] - 1))[None], metrica)[0]
                else:
                    D[k, c] = np.nan
    else:  # amostra mais próxima
        for k in range(len(Fp)):
            d = dist_vec(Fp[k], Fg, metrica)
            if loo:
                d[k] = np.inf
            for c in range(nC):
                D[k, c] = d[idx[c]].min()
            if loo and cont[yg[k]] < 2:
                D[k, yg[k]] = np.nan
    return D


def pontuar(D, ci, loo):
    """ci = índice da classe verdadeira (-1 = pessoa fora do banco)."""
    m = len(D)
    ar = np.arange(m)
    Dn = np.where(np.isnan(D), np.inf, D)
    pred, dmin = Dn.argmin(1), Dn.min(1)
    if loo:
        gen = ~np.isnan(D[ar, ci])
        Dimp = Dn.copy()
        Dimp[ar, ci] = np.inf
        imp = np.ones(m, bool)
    else:
        gen = ci >= 0
        Dimp = Dn
        imp = ci < 0
    ok = pred == ci
    s_g = np.where(ok, dmin, np.inf)[gen]          # aceito E com a identidade certa
    s_i = Dimp.min(1)[imp]                          # menor distância de um impostor
    return dict(s_g=s_g, s_i=s_i, rank1=ok[gen].mean() if gen.any() else np.nan,
                imp_ident=Dimp.argmin(1)[imp], erro_ident=(pred[gen & ~ok], ci[gen & ~ok]),
                gen_min=dmin[gen], gen_ok=ok[gen])


def curvas(s_g, s_i):
    fin = np.concatenate([s_g[np.isfinite(s_g)], s_i[np.isfinite(s_i)]])
    T = np.unique(fin)
    sg, si = np.sort(s_g), np.sort(s_i)
    far = np.searchsorted(si, T, side="right") / len(si)
    frr = 1 - np.searchsorted(sg, T, side="right") / len(sg)
    return T, far, frr


def resumo(T, far, frr, alvo):
    ok = np.where(far <= alvo)[0]
    if len(ok) == 0:
        return np.nan, np.nan
    j = ok.max()
    return frr[j], T[j]


# ----------------------------------------------------------------------------
# Diagnóstico: quais células mais pesam na distância euclidiana atual?
# ----------------------------------------------------------------------------
def peso_celulas(F, y, nC):
    S = np.zeros((nC, F.shape[1]))
    np.add.at(S, y, F)
    C = S / np.bincount(y, minlength=nC)[:, None]
    acc, n = np.zeros(GRID * GRID), 0
    for k in range(len(F)):
        outros = [j for j in range(nC) if j != y[k]]
        d2 = (F[k] - C[outros]) ** 2
        acc += (d2.reshape(len(outros), GRID * GRID, -1).sum(2) / d2.sum(1, keepdims=True)).sum(0)
        n += len(outros)
    return (100 * acc / n).reshape(GRID, GRID)


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", default="imagens_processadas")
    ap.add_argument("--teste", default=None, help="pasta com fotos de teste (outra sessão)")
    ap.add_argument("--saida", default=".")
    a = ap.parse_args()

    imgs, nomes = carregar(a.pasta)
    classes = sorted(set(nomes))
    if len(classes) < 2:
        raise SystemExit("Preciso de pelo menos 2 pessoas em " + a.pasta)
    cidx = {n: i for i, n in enumerate(classes)}
    yg = np.array([cidx[n] for n in nomes])
    nC = len(classes)
    print(f"Banco: {len(imgs)} imagens, {nC} pessoas")
    for n, c in zip(classes, np.bincount(yg)):
        print(f"  {n:15s} {c:3d} fotos" + ("   <-- só 1 foto: não dá para avaliar" if c < 2 else ""))
    print("  (centroides com poucas fotos são ruidosos e ficam mais longe de todo mundo)\n")

    cods = [codigos_mblbp(im) for im in imgs]
    if a.teste:
        timgs, tnomes = carregar(a.teste)
        tcods = [codigos_mblbp(im) for im in timgs]
        yt = np.array([cidx.get(n, -1) for n in tnomes])
        desc = sorted(set(n for n in tnomes if n not in cidx))
        print(f"Teste externo: {len(timgs)} imagens; fora do banco (impostores): {desc or 'nenhuma'}\n")

    resultados = {}
    for nome_v, cfg in VARIANTES.items():
        Fg = np.array([feature(c, cfg) for c in cods])
        Ft = np.array([feature(c, cfg) for c in tcods]) if a.teste else None
        for clf in ("centroide", "amostra"):
            r = {}
            D = dist_classes(Fg, yg, nC, Fg, True, clf, cfg["dist"])
            r["loo"] = pontuar(D, yg, True)
            if a.teste:
                Dt = dist_classes(Fg, yg, nC, Ft, False, clf, cfg["dist"])
                r["ext"] = pontuar(Dt, yt, False)
            resultados[(nome_v, clf)] = r

    figs = {}
    for modo, titulo in (("loo", "LEAVE-ONE-OUT (fotos de cadastro; otimista)"),
                         ("ext", "TESTE EXTERNO (outra sessão; o que vale)")):
        if modo == "ext" and not a.teste:
            continue
        print("=" * 112)
        print(titulo)
        print(f"{'variante':54s} {'clf':9s} {'rank1':>6s} {'EER':>6s} {'T_EER':>8s} "
              f"{'FRR@FAR5%':>10s} {'FRR@FAR1%':>10s} {'T@FAR1%':>8s}")
        linhas = []
        for (nv, clf), r in resultados.items():
            s = r[modo]
            if len(s["s_g"]) == 0 or len(s["s_i"]) == 0:
                continue
            T, far, frr = curvas(s["s_g"], s["s_i"])
            i = np.argmin(np.abs(far - frr))
            eer = (far[i] + frr[i]) / 2
            f5, _ = resumo(T, far, frr, 0.05)
            f1, t1 = resumo(T, far, frr, 0.01)
            linhas.append((eer, nv, clf, s["rank1"], T[i], f5, f1, t1, (T, far, frr)))
        for eer, nv, clf, r1, ti, f5, f1, t1, _ in sorted(linhas, key=lambda x: x[0]):
            print(f"{nv:54s} {clf:9s} {r1:6.1%} {eer:6.1%} {ti:8.3f} {f5:10.1%} {f1:10.1%} {t1:8.3f}")
        figs[modo] = sorted(linhas, key=lambda x: x[0])
        print("  rank1 = acerto de identidade; EER = ponto em que FAR=FRR (menor é melhor);")
        print("  FRR@FAR1% = quantos usuários legítimos são barrados quando só 1% dos impostores entra.\n")

    # --- imãs: quem "atrai" os impostores e os erros de identidade (variante A, centroide)
    chave = (list(VARIANTES)[0], "centroide")
    modo = "ext" if a.teste else "loo"
    s = resultados[chave][modo]
    print("=" * 112)
    print("IMAS (variante A atual): para quem os desconhecidos / erros apontam")
    tot = Counter(s["imp_ident"])
    for c, q in tot.most_common(4):
        print(f"  impostor -> {classes[c]:12s} {q / len(s['imp_ident']):6.1%}")
    pred_err, ver_err = s["erro_ident"]
    if len(pred_err):
        print("  erros de identidade (verdadeiro -> previsto):")
        for (v, p), q in Counter(zip(ver_err, pred_err)).most_common(6):
            print(f"    {classes[v]:12s} -> {classes[p]:12s} {q}x")

    Fa = np.array([feature(c, VARIANTES[chave[0]]) for c in cods])
    print("\nPESO de cada célula 5x5 na distância euclidiana atual (% do total; linha 5 = queixo/barba):")
    pc = peso_celulas(Fa, yg, nC)
    for linha in pc:
        print("   " + "  ".join(f"{v:5.1f}" for v in linha))
    print("  (se as células da última linha/coluna passam muito de 4%, a distância está sendo dominada por elas)\n")

    # --- figura
    modo_f = "ext" if a.teste else "loo"
    linhas = figs[modo_f]
    fig, ax = plt.subplots(1, 3, figsize=(17, 4.8))
    base = [l for l in linhas if l[1].startswith("A") and l[2] == "centroide"][0]
    melhores = [base] + [l for l in linhas if l is not base][:3]
    for eer, nv, clf, *_, cur in melhores:
        T, far, frr = cur
        ax[0].plot(far * 100, frr * 100, label=f"{nv[:22]}… {clf} (EER {eer:.1%})")
    ax[0].set_xlabel("FAR % (impostor entra)")
    ax[0].set_ylabel("FRR % (legítimo barrado)")
    ax[0].set_title("Curva DET: mais perto da origem = melhor")
    ax[0].legend(fontsize=7)
    ax[0].grid(alpha=.3)
    for k, (eer, nv, clf, _, ti, _, _, _, cur) in enumerate((base, linhas[0])):
        T, far, frr = cur
        ax[1].plot(T / T.max(), far * 100, f"C{k}--", label=f"FAR  {nv[:1]} {clf}")
        ax[1].plot(T / T.max(), frr * 100, f"C{k}-", label=f"FRR  {nv[:1]} {clf}")
    ax[1].set_xlabel("limiar (normalizado pelo máximo de cada variante)")
    ax[1].set_ylabel("%")
    ax[1].set_title("FAR e FRR x limiar: A (atual) vs melhor")
    ax[1].legend(fontsize=7)
    ax[1].grid(alpha=.3)
    for k, (nv, clf) in enumerate([chave, (linhas[0][1], linhas[0][2])]):
        s = resultados[(nv, clf)][modo_f]
        g = s["s_g"][np.isfinite(s["s_g"])]
        sc = lambda x: x / max(g.max(), s["s_i"].max())
        ax[2].hist(sc(g), bins=25, alpha=.45, color=f"C{k}", label=f"legítimo {nv[:1]}")
        ax[2].hist(sc(s["s_i"]), bins=25, alpha=.45, color=f"C{k+2}", label=f"impostor {nv[:1]}")
    ax[2].set_title("Distribuição das distâncias (quanto menos sobrepostas, melhor)")
    ax[2].legend(fontsize=7)
    plt.tight_layout()
    out = os.path.join(a.saida, "curvas_limiar.png")
    fig.savefig(out, dpi=130)
    print(f"Figura salva em {out}")


if __name__ == "__main__":
    main()