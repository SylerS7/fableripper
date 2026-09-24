import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.extractor import clean_title_str

cases = [
    ("Chapter 301 Sudden Appearance of a Dou Huang&amp;#39;s Presence",
     "Chapter 301 Sudden Appearance of a Dou Huang's Presence"),
    ("Chapter 303 Jia Lao&amp;#39;s Strength",
     "Chapter 303 Jia Lao's Strength"),
    ("Chapter 308\xa0 The Overly Simple Second Round",
     "Chapter 308 The Overly Simple Second Round"),
    ("Chapter 300 The End", "Chapter 300 The End"),
    ("  Chapter  297   Mu Zhan  ", "Chapter 297 Mu Zhan"),
]

all_passed = True
for raw, expected in cases:
    result = " ".join(clean_title_str(raw).split())
    exp = " ".join(expected.split())
    ok = result == exp
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {raw[:60]}")
    print(f"        => {result}")
    if not ok:
        print(f"   Expect: {exp}")
        all_passed = False

print()
if all_passed:
    print("ALL TITLE CLEANING TESTS PASSED!")
else:
    print("SOME TESTS FAILED!")
    sys.exit(1)
