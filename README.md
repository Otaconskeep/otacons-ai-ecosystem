# Otacon

A local AI platform with a hardware-aware setup wizard. Runtime configuration is written outside this repository.

```bash
python3 -m unittest discover -s tests -v
PYTHONPATH=. python3 -m installer.cli --name Billy --features chat,memory,voice --output ~/.config/otacon
```
