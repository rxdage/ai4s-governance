# Synthetic messy lab

A reproducible "bad data" folder for trying `ai4s audit` and for writing about it.

```bash
python examples/build_messy_lab.py --force
ai4s audit examples/messy-lab --label "Synthetic messy lab" --out /tmp/messy-report.md
```

## What is in it

115 files, built from the failure modes in the playbook:

| Group | Files | Why |
|---|---:|---|
| short IDs | 30 | `R37_W1_D0000...` — no four-digit padding |
| Chinese + hyphen + space | 20 | `R0037-W01-01_after 丙酮擦拭.jpg` |
| version names | 15 | `final_v2.csv`, `final_final.csv`, `copy of data.csv` |
| instrument names | 15 | `Channel_00_for_filterData_2026-07-22-17-00-31.csv` |
| pure serials | 15 | `dna034.abf` |
| valid syntax, unregistered type | 10 | `...__XYZ__...` |
| no extension | 5 | `..._RUN0000` |
| duplicate full names | 5 | same name in `archive/` |

## Expected audit result

```
115 files, 15 parseable (13.0%), 5 duplicate name(s), 0 sidecar(s)
CHARSET_INVALID 37
ZONE1_SYNTAX    30
ZONE_COUNT      28
EXT_MISSING      5
```

The point is not the exact numbers. It is that a folder can look "organized" to a
human and still be unreadable to an agent: 87% of these synthetic names cannot be parsed
without opening the file.

The generator does not modify anything outside its own folder. `ai4s audit` is
read-only.

## Names-only mode

If a lab will not send files, it can send a list of relative paths — one per
line, no contents:

```bash
# Linux/macOS
find . -type f -printf '%P\n' > names.txt

# Windows PowerShell (run inside the data folder)
Get-ChildItem -Recurse -File | ForEach-Object { $_.FullName.Substring((Get-Location).Path.Length + 1).Replace('\','/') } | Set-Content names.txt
```

```bash
ai4s audit --names names.txt --label "Lab A" --out audit_report.md
```

This gives the same shape metrics (parseable %, top errors, duplicates, legacy
patterns) without reading any file content. Bytes and sidecars are not counted.

