# Matchi.se HTML Structure Notes

## Target URL

```
https://www.matchi.se/book/schedule?facilityId=<id>&date=<YYYY-MM-DD>&sport=1
```

| Query parameter | Value |
|----------------|-------|
| `facilityId`   | Integer facility ID (see `facilities.py`) |
| `date`         | Date in `YYYY-MM-DD` format |
| `sport`        | `1` = tennis |

No authentication is required.  The page is publicly accessible.

## CSS Selector

Available court slots are represented as `<td>` elements with **both** the
`slot` and `free` CSS classes:

```html
<td class="slot free" title="...">
```

Unavailable (booked) slots use different class combinations such as
`slot booked` or `slot reserved` and are ignored.

## Title Attribute Parsing

Each available `<td class="slot free">` carries a `title` attribute whose
content uses literal `<br>` strings (not real HTML line breaks) as separators:

```
<part0><br><part1><br><part2>
```

| Index | Content | Example |
|-------|---------|---------|
| `[0]` | Unused header / label text | `"Tilgjengelig"` |
| `[1]` | Court name | `"Bane 3"` |
| `[2]` | Time-slot label | `"17:00-18:00"` |

### Parsing logic (Python)

```python
parts = slot["title"].split("<br>")
court      = parts[1].strip()   # e.g. "Bane 3"
time_label = parts[2].strip()   # e.g. "17:00-18:00"
```

Slots where `len(parts) < 3`, or where `court`/`time_label` are empty after
stripping, are silently skipped to tolerate future HTML structure changes.

## Data Structure Produced

```python
{
    "17:00-18:00": ["Bane 1", "Bane 3"],
    "18:00-19:00": ["Bane 2"],
}
```

Keys are the raw time-slot label strings taken directly from the HTML — they
are **not** normalised.

## Notes

- No rate limiting has been observed, but the monitor uses 5-minute poll
  intervals to be a good citizen.
- If Matchi changes their HTML structure the only code that needs updating is
  `parse_slots_from_html()` in `scraper.py`.
- The `wl` query parameter is passed as an empty string to match the URL
  pattern used by the live site; omitting it still works but may change in
  future.
