# Zmanim PDF Generator

Generates a full-year halachic times (zmanim) PDF calendar for Pleasantville, NJ (2026) or any other specified city in the world.

## Output

A landscape-format PDF with one table per month, showing daily zmanim (halachic times), Hebrew dates, parshiot, holidays, candle lighting times, and molad announcements.

## Usage

```bash
python3 zemanim.py [--city "City, State"]
```

Output is written to `./output/zmanim_<cityname>_2026.pdf`.

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--city "City, State"` | City name to geocode for zmanim calculations | `"Pleasantville, NJ"` |

### Examples

```bash
# Default — Pleasantville, NJ
python3 zemanim.py

# Any city in the world
python3 zemanim.py --city "Brooklyn, NY"
python3 zemanim.py --city "Los Angeles, CA"
python3 zemanim.py --city "Jerusalem, Israel"
```

The city name is geocoded automatically; latitude, longitude, and timezone are resolved from the result.

## Dependencies

```bash
pip3 install reportlab zmanim
```

Fonts are bundled in `./fonts/`: Source Sans 3 (Regular and Bold) & Noto Sans Hebrew (Regular and Bold).

## Features

- Daily zmanim per GRA/standard opinion (sha'ot zmaniyot sunrise–sunset)
- Alot hashachar at 16.1° depression; Tzait hakochavim at 8.5°
- Candle lighting 18 minutes before sunset for Shabbat and Yom Tov
- Hebrew dates, parshiot, and holiday labels in Hebrew
- Special Shabbatot (Shira, Shekalim, Zachor, Parah, HaChodesh, HaGadol, Chazon, Nachamu, Shuva)
- Shabbat Mevarchim molad table
- DST handled automatically via `America/New_York` timezone

## Adapting for Other Years or Locations

To change **location**: update the `LOCATION` constant (`GeoLocation`) — timezone, DST, and solar math adjust automatically.

To change **year**: update the output filename and the `months_rc` list in `_build_molad_table()`. The `_RH_YEAR` dict may need a new entry for the new year's Hebrew name.

## License

MIT — see [LICENSE](LICENSE).