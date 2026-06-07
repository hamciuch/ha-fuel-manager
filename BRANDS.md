# Ikona i wersje w HACS

## Dlaczego HACS pokazuje skróty commitów (np. `6d048ac`) zamiast `1.1.0`

HACS śledzi **Release'y** GitHuba. Jeśli repo nie ma opublikowanych wydań,
HACS pokazuje gałąź i wyświetla skróty commitów jako „wersję”. Rozwiązanie:
opublikuj Release dla taga.

```bash
# 1) wypchnij tagi
git push origin --tags

# 2) opublikuj Release (GitHub CLI)
gh release create v1.1.0 --title "v1.1.0" \
  --notes "Statystyki czasowe z importu, pełna historia, lokalizacja z telefonu, import z /config i /media."
```

Bez `gh`: GitHub → **Releases** → *Draft a new release* → wybierz tag `v1.1.0`
→ *Publish release*. To uruchomi też workflow, który wstrzyknie wersję do
`manifest.json` i podepnie `fuel_manager.zip`.

Potem w HACS: otwórz integrację → **Redownload** → wybierz wersję `1.1.0`.
Od tej pory „Zainstalowana / Ostatnia wersja” będą semantyczne.

> Numer w `manifest.json` ma odpowiadać tagowi (teraz `1.1.0`). Kolejne wydania:
> podbij tag (`v1.1.1`, `v1.2.0`…) i opublikuj Release.

## Ikona („icon not available”)

Ikony integracji w HA/HACS pochodzą z repo **`home-assistant/brands`** — nie da
się ich nadpisać lokalnie. Gotowe pliki są w `assets/brands/`. Aby ikona się
pojawiła, wyślij je PR-em do brands:

1. Sforkuj `https://github.com/home-assistant/brands`.
2. Skopiuj katalog `assets/brands/custom_integrations/fuel_manager/`
   do `custom_integrations/fuel_manager/` w forku (pliki: `icon.png` 256×256,
   `icon@2x.png` 512×512; `logo*.png` opcjonalnie).
3. Commit + PR. Po zmerge’owaniu ikona pojawi się automatycznie (czasem po
   odświeżeniu/restarcie).

Wymogi brands: PNG, przezroczyste tło, `icon.png` dokładnie 256×256,
`icon@2x.png` 512×512, wytrymowane do treści. Dostarczone pliki to spełniają.

Źródło ikony: `assets/icon_src.svg` (możesz edytować i wyrenderować ponownie).
