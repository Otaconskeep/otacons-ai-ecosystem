import unittest
from pathlib import Path
class BrandingTests(unittest.TestCase):
 def test_central_branding(self):
  b=Path('config/branding.yaml').read_text(); self.assertIn('Antonio Garcia',b); self.assertIn('Designed & Engineered by Antonio Garcia',b); self.assertIn('Copyright © 2026 Antonio Garcia',b)
 def test_public_docs_credit(self):
  for p in ('README.md','CHANGELOG.md','CONTRIBUTING.md','SECURITY.md'): self.assertIn('Antonio Garcia',Path(p).read_text())
