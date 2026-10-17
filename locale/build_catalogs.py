"""Build gettext catalogs (.po + compiled .mo) for SportIQ interface languages without needing GNU gettext.

DRAFT TRANSLATIONS: produced for the pilot and must be reviewed by qualified translators before public launch
(blueprint Module 7: "reviewed translations"). Edit the table below, then run:  python locale/build_catalogs.py
"""
import array
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent

#          msgid                         pcm                         yo                               ha                              ig
T = {
    "Home": ("Home", "Ilé", "Gida", "Ụlọ"),
    "Explore courses": ("Check courses", "Ṣàwárí àwọn ẹ̀kọ́", "Bincika kwasa-kwasai", "Chọgharịa ọmụmụ"),
    "My learning": ("My learning", "Ẹ̀kọ́ mi", "Karatuna", "Mmụta m"),
    "Academy": ("Academy", "Ilé-ẹ̀kọ́", "Makaranta", "Ụlọ akwụkwọ"),
    "Live academy": ("Live class", "Kíláàsì tààrà", "Aji kai tsaye", "Klas ndụ"),
    "Practical labs": ("Practice labs", "Yàrá ìdánrawò", "Dakunan gwaji", "Ụlọ nyocha omume"),
    "Sports library": ("Sports library", "Ilé-ìkàwé eré ìdárayá", "Ɗakin karatun wasanni", "Ọba akwụkwọ egwuregwu"),
    "AI study assistant": ("AI study helper", "Olùrànlọ́wọ́ ẹ̀kọ́ AI", "Mataimakin karatu na AI", "Onye enyemaka ọmụmụ AI"),
    "Research & insights": ("Research", "Ìwádìí", "Bincike", "Nchọcha"),
    "Qualifications": ("Qualifications", "Ìwé-ẹ̀rí", "Cancanta", "Asambodo"),
    "Credentials": ("My certificates", "Ìwé-ẹ̀rí mi", "Takardun shaida", "Asambodo m"),
    "CPD & renewals": ("CPD & renew", "CPD àti ìsọdọ̀tun", "CPD da sabuntawa", "CPD na mmeghari"),
    "Achievements": ("Wetin I don achieve", "Àṣeyọrí", "Nasarori", "Ihe m rụzuru"),
    "Careers & community": ("Work & community", "Iṣẹ́ àti àwùjọ", "Sana'a da al'umma", "Ọrụ na obodo"),
    "Community": ("Community", "Àwùjọ", "Al'umma", "Obodo"),
    "Opportunities": ("Opportunities", "Àǹfààní", "Damammaki", "Ohere"),
    "Experience & CV": ("Experience & CV", "Ìrírí àti CV", "Ƙwarewa da CV", "Ahụmahụ na CV"),
    "Challenges": ("Challenges", "Ìpèníjà", "Ƙalubale", "Ihe ịma aka"),
    "Me": ("Me", "Èmi", "Ni", "Mụ"),
    "Professional profile": ("My work profile", "Àkọsílẹ̀ iṣẹ́ mi", "Bayanan sana'ata", "Profaịlụ ọrụ m"),
    "Account settings": ("Account settings", "Ètò àkáǹtì", "Saitunan asusu", "Ntọala akaụntụ"),
    "Help & support": ("Help", "Ìrànlọ́wọ́", "Taimako", "Enyemaka"),
    "Report a concern": ("Report wahala", "Fi ẹ̀sùn kan hàn", "Kai rahoton damuwa", "Kọọ nsogbu"),
    "Back office": ("Back office", "Back office", "Back office", "Back office"),
    "Log out": ("Comot", "Jáde", "Fita", "Pụọ"),
    "Language": ("Language", "Èdè", "Harshe", "Asụsụ"),
    "Explore": ("Check am", "Ṣàwárí", "Bincika", "Chọgharịa"),
    "Learning": ("Learning", "Ẹ̀kọ́", "Karatu", "Mmụta"),
    "Search courses, topics, sports…": ("Find course, topic, sport…", "Wá ẹ̀kọ́, àkòrí, eré…", "Nemo kwas, batu, wasa…", "Chọọ ọmụmụ, isiokwu, egwuregwu…"),
    # Public website navigation
    "About SportIQ": ("About SportIQ", "Nípa SportIQ", "Game da SportIQ", "Maka SportIQ"),
    "Resources": ("Resources", "Àwọn ohun èlò", "Albarkatu", "Akụrụngwa"),
    "For institutions": ("For organisations", "Fún àwọn ilé-iṣẹ́", "Don cibiyoyi", "Maka ụlọ ọrụ"),
    "Verify": ("Check am", "Ṣàyẹ̀wò", "Tabbatar", "Nyochaa"),
    "Verify a certificate": ("Check certificate", "Ṣàyẹ̀wò ìwé-ẹ̀rí", "Tabbatar da takardar shaida", "Nyochaa asambodo"),
    "Course catalogue": ("All courses", "Àkójọ ẹ̀kọ́", "Jerin kwasa-kwasai", "Ndepụta ọmụmụ"),
    "Learning paths": ("Learning road", "Ọ̀nà ẹ̀kọ́", "Hanyoyin karatu", "Ụzọ mmụta"),
    "Certifications": ("Certificates", "Ìwé-ẹ̀rí", "Takardun shaida", "Asambodo"),
    "FAQs": ("Questions wey people dey ask", "Àwọn ìbéèrè tí a máa ń béèrè", "Tambayoyi da ake yawan yi", "Ajụjụ a na-ajụkarị"),
    "Blog": ("Blog", "Búlọ́ọ̀gù", "Blog", "Blọọgụ"),
    "Events": ("Events", "Àwọn ìṣẹ̀lẹ̀", "Abubuwan da ke tafe", "Mmemme"),
    "Help centre": ("Help centre", "Ibùdó ìrànlọ́wọ́", "Cibiyar taimako", "Ebe enyemaka"),
    "Sign up": ("Join", "Forúkọsílẹ̀", "Yi rajista", "Debanye aha"),
    "Sign up free": ("Join free", "Forúkọsílẹ̀ lọ́fẹ̀ẹ́", "Yi rajista kyauta", "Debanye aha n'efu"),
    "Login": ("Enter", "Wọlé", "Shiga", "Banye"),
    "Request a demo": ("Ask for demo", "Béèrè àfihàn", "Nemi nunin", "Rịọ ngosi"),
    "Request demo": ("Ask for demo", "Béèrè àfihàn", "Nemi nunin", "Rịọ ngosi"),
    "My dashboard": ("My dashboard", "Pátákó mi", "Allon bayanaina", "Dashboard m"),
    "Dashboard": ("Dashboard", "Pátákó", "Allon bayanai", "Dashboard"),
    "Organisation": ("Organisation", "Àjọ", "Ƙungiya", "Nzukọ"),
    "Observatory": ("Observatory", "Ibùdó àkíyèsí", "Cibiyar sa ido", "Ebe nleba anya"),
    "Frequently asked questions": ("Questions wey people dey ask", "Àwọn ìbéèrè tí a máa ń béèrè", "Tambayoyi da ake yawan yi", "Ajụjụ a na-ajụkarị"),
    "Interface translations are drafts awaiting expert review.": (
        "Dis translation still be draft wey experts go check.", "Ìtumọ̀ yìí ṣì jẹ́ àkọ́kọ́ tí àwọn amòye yóò ṣàyẹ̀wò.",
        "Wannan fassara daftari ce da ƙwararru za su duba.", "Ntụgharị a bụ ụdị mbụ ndị ọkachamara ga-enyocha."),
}
LANGS = ["pcm", "yo", "ha", "ig"]


def write_mo(path, catalog):
    keys = sorted(catalog)
    ids = b"".join(k.encode() + b"\0" for k in keys)
    strs = b"".join(catalog[k].encode() + b"\0" for k in keys)
    offsets, o_id, o_str = [], 0, 0
    for k in keys:
        offsets.append((len(k.encode()), o_id, len(catalog[k].encode()), o_str))
        o_id += len(k.encode()) + 1
        o_str += len(catalog[k].encode()) + 1
    n = len(keys)
    key_start = 7 * 4 + 16 * n
    value_start = key_start + len(ids)
    koffsets, voffsets = [], []
    for l1, o1, l2, o2 in offsets:
        koffsets += [l1, o1 + key_start]
        voffsets += [l2, o2 + value_start]
    header = array.array("I", [0x950412de, 0, n, 7 * 4, 7 * 4 + n * 8, 0, 0])
    with open(path, "wb") as fh:
        fh.write(header.tobytes())
        fh.write(array.array("I", koffsets).tobytes())
        fh.write(array.array("I", voffsets).tobytes())
        fh.write(ids)
        fh.write(strs)


for i, lang in enumerate(LANGS):
    folder = HERE / lang / "LC_MESSAGES"
    os.makedirs(folder, exist_ok=True)
    catalog = {"": f"Content-Type: text/plain; charset=UTF-8\nLanguage: {lang}\n"}
    po = [f'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n"Language: {lang}\\n"\n']
    for msgid, values in T.items():
        catalog[msgid] = values[i]
        po.append(f'#, fuzzy\nmsgid "{msgid}"\nmsgstr "{values[i]}"\n')
    (folder / "django.po").write_text("\n".join(po), encoding="utf-8")
    write_mo(folder / "django.mo", catalog)
print("Built catalogs for", ", ".join(LANGS))
