"""Icône de l'application, tirée de la bannière « Analyse des rapports des CB » (packaging/banniere.jpg).

La loupe de la bannière (lentille avec le graphique) est découpée en disque et complétée d'un manche, sur fond
transparent. Les petites tailles (16 et 24 pixels) n'utilisent que la lentille, plus lisible.
Produit packaging/icone.ico (16 à 256 pixels) et packaging/icone.png (256 pixels).

Usage : python packaging/composer_icone.py
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

DOSSIER = Path(__file__).resolve().parent
CENTRE, RAYON = (775, 247), 155  # loupe dans la bannière (anneau métallique compris)


def _disque(image: Image.Image, diametre: int) -> Image.Image:
    cx, cy = CENTRE
    d = image.crop((cx - RAYON, cy - RAYON, cx + RAYON, cy + RAYON)).resize((diametre, diametre), Image.LANCZOS)
    masque = Image.new("L", (diametre * 4, diametre * 4), 0)
    ImageDraw.Draw(masque).ellipse((0, 0, diametre * 4 - 1, diametre * 4 - 1), fill=255)
    d.putalpha(masque.resize((diametre, diametre), Image.LANCZOS))
    return d


def loupe(image: Image.Image, n: int = 1024) -> Image.Image:
    """Loupe complète : lentille, bague métallique et manche bleu marine dans l'axe à 45°."""
    k = n / 1024
    toile = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    diam = int(760 * k)
    centre, r = (int(40 * k) + diam // 2, int(40 * k) + diam // 2), diam // 2
    u = (math.cos(math.radians(45)), math.sin(math.radians(45)))
    ech = 4
    grand = Image.new("RGBA", (n * ech, n * ech), (0, 0, 0, 0))
    g = ImageDraw.Draw(grand)

    def trait(d0, d1, largeur, couleur):
        a = (centre[0] + u[0] * d0, centre[1] + u[1] * d0)
        b = (centre[0] + u[0] * d1, centre[1] + u[1] * d1)
        pa, pb, w = (a[0] * ech, a[1] * ech), (b[0] * ech, b[1] * ech), largeur * k * ech
        g.line([pa, pb], fill=couleur, width=int(w))
        for p in (pa, pb):
            g.ellipse((p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2), fill=couleur)
    trait(r - 20 * k, r + 95 * k, 104, (150, 163, 182, 255))   # bague (gris acier)
    trait(r - 20 * k, r + 95 * k, 70, (205, 214, 226, 255))    # reflet de la bague
    trait(r + 95 * k, r + 330 * k, 128, (16, 40, 74, 255))     # manche bleu marine
    trait(r + 110 * k, r + 315 * k, 34, (52, 92, 150, 255))    # reflet du manche
    toile.alpha_composite(grand.resize((n, n), Image.LANCZOS))
    ombre = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(ombre).ellipse((centre[0] - r + 10 * k, centre[1] - r + 18 * k,
                                   centre[0] + r + 10 * k, centre[1] + r + 18 * k), fill=(16, 40, 74, 70))
    toile.alpha_composite(ombre.filter(ImageFilter.GaussianBlur(14 * k)))
    toile.alpha_composite(_disque(image, diam), (centre[0] - r, centre[1] - r))
    return toile


def lentille_seule(image: Image.Image, n: int) -> Image.Image:
    toile = Image.new("RGBA", (n * 8, n * 8), (0, 0, 0, 0))
    toile.alpha_composite(_disque(image, n * 8), (0, 0))
    return toile.resize((n, n), Image.LANCZOS)


def main() -> None:
    banniere = Image.open(DOSSIER / "banniere.jpg").convert("RGBA")
    grande = loupe(banniere)
    images = {t: grande.resize((t, t), Image.LANCZOS) for t in (32, 48, 64, 128, 256)}
    images.update({t: lentille_seule(banniere, t) for t in (16, 24)})
    images[256].save(DOSSIER / "icone.png")
    tailles = sorted(images)
    images[256].save(DOSSIER / "icone.ico", sizes=[(t, t) for t in tailles],
                     append_images=[images[t] for t in tailles if t != 256])


if __name__ == "__main__":
    main()
