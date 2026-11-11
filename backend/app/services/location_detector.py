"""Indian Location and State Identification Service for CPASS.

Identifies Indian states from free-text locations such as:
- City names (Chennai -> Tamil Nadu, Ludhiana -> Punjab, Hyderabad -> Telangana, etc.)
- District names across Indian states
- State names, acronyms, and aliases (e.g. TN, PB, TS, AP, RJ, KL, WB, UP, GJ, OD, BR, MZ, PY)
- City and state combinations ("Ludhiana, Punjab", "Whitefield, Bengaluru, Karnataka")
- Common spelling variations and historical names (Madras, Calcutta, Baroda, Vizag, Kovai, Trichy, Cochin, Trivandrum, etc.)
- 6-digit Indian PIN codes using postal index routing
- Flags ambiguous multi-state locations (e.g. Bilaspur, Aurangabad)
- Classifies whether the detected state is supported in the statutory 13-state minimum wage register.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from ..auth import ALL_13_STATES, STATE_ALIASES, resolve_state

# Supported states in the statutory minimum wage master (455 records)
SUPPORTED_13_STATES: frozenset[str] = frozenset(ALL_13_STATES)

# All standard Indian States and Union Territories
ALL_INDIAN_STATES: frozenset[str] = frozenset({
    # 13 CPASS Master States
    "ANDHRA PRADESH",
    "BIHAR",
    "GUJARAT",
    "KERALA",
    "MIZORAM",
    "ODISHA",
    "PUDUCHERRY",
    "PUNJAB",
    "RAJASTHAN",
    "TAMIL NADU",
    "TELANGANA",
    "UTTAR PRADESH",
    "WEST BENGAL",
    # Other Indian States
    "ASSAM",
    "CHHATTISGARH",
    "GOA",
    "HARYANA",
    "HIMACHAL PRADESH",
    "JHARKHAND",
    "KARNATAKA",
    "MADHYA PRADESH",
    "MAHARASHTRA",
    "MANIPUR",
    "MEGHALAYA",
    "NAGALAND",
    "SIKKIM",
    "TRIPURA",
    "UTTARAKHAND",
    "ARUNACHAL PRADESH",
    # Union Territories
    "DELHI",
    "CHANDIGARH",
    "JAMMU AND KASHMIR",
    "LADAKH",
    "ANDAMAN AND NICOBAR ISLANDS",
    "DADRA AND NAGAR HAVELI AND DAMAN AND DIU",
    "LAKSHADWEEP",
})

# Comprehensive aliases for non-13 Indian states & UTs
NON_13_STATE_ALIASES: dict[str, str] = {
    # Karnataka
    "ka": "KARNATAKA",
    "karnataka": "KARNATAKA",
    "kar": "KARNATAKA",
    # Maharashtra
    "mh": "MAHARASHTRA",
    "maharashtra": "MAHARASHTRA",
    "maha": "MAHARASHTRA",
    # Delhi
    "dl": "DELHI",
    "delhi": "DELHI",
    "nct": "DELHI",
    "new delhi": "DELHI",
    "newdelhi": "DELHI",
    # Haryana
    "hr": "HARYANA",
    "haryana": "HARYANA",
    # Madhya Pradesh
    "mp": "MADHYA PRADESH",
    "madhya pradesh": "MADHYA PRADESH",
    "madhyapradesh": "MADHYA PRADESH",
    # Jharkhand
    "jh": "JHARKHAND",
    "jharkhand": "JHARKHAND",
    # Chhattisgarh
    "cg": "CHHATTISGARH",
    "chhattisgarh": "CHHATTISGARH",
    "chattisgarh": "CHHATTISGARH",
    # Assam
    "as": "ASSAM",
    "assam": "ASSAM",
    # Uttarakhand
    "uk": "UTTARAKHAND",
    "uttarakhand": "UTTARAKHAND",
    "uttaranchal": "UTTARAKHAND",
    # Himachal Pradesh
    "hp": "HIMACHAL PRADESH",
    "himachal pradesh": "HIMACHAL PRADESH",
    "himachal": "HIMACHAL PRADESH",
    # Goa
    "ga": "GOA",
    "goa": "GOA",
    # Chandigarh
    "ch": "CHANDIGARH",
    "chandigarh": "CHANDIGARH",
    # Jammu & Kashmir
    "jk": "JAMMU AND KASHMIR",
    "jammu": "JAMMU AND KASHMIR",
    "kashmir": "JAMMU AND KASHMIR",
    "jammu and kashmir": "JAMMU AND KASHMIR",
    "jammu & kashmir": "JAMMU AND KASHMIR",
    # Ladakh
    "ladakh": "LADAKH",
    # Tripura
    "tr": "TRIPURA",
    "tripura": "TRIPURA",
    # Meghalaya
    "ml": "MEGHALAYA",
    "meghalaya": "MEGHALAYA",
    # Manipur
    "mn": "MANIPUR",
    "manipur": "MANIPUR",
    # Nagaland
    "nl": "NAGALAND",
    "nagaland": "NAGALAND",
    # Sikkim
    "sk": "SIKKIM",
    "sikkim": "SIKKIM",
    # Arunachal Pradesh
    "ar": "ARUNACHAL PRADESH",
    "arunachal pradesh": "ARUNACHAL PRADESH",
}

# -----------------------------------------------------------------------------
# 6-Digit Indian Postal Index Number (PIN) Prefix Mapping
# -----------------------------------------------------------------------------
PIN_3_DIGIT_MAP: dict[str, str] = {
    # Puducherry (605xxx enclave in Tamil Nadu)
    "605": "PUDUCHERRY",
    # Lakshadweep
    "682": "KERALA",  # (Mainland Kochi is 682, Islands 682555)
    # Andaman & Nicobar
    "744": "ANDAMAN AND NICOBAR ISLANDS",
    # Daman & Diu
    "396": "GUJARAT",  # (Daman 396210, Diu 362520)
    # Goa (403xxx enclave in Maharashtra zone)
    "403": "GOA",
    # Sikkim
    "737": "SIKKIM",
    # Arunachal Pradesh
    "790": "ARUNACHAL PRADESH",
    "791": "ARUNACHAL PRADESH",
    "792": "ARUNACHAL PRADESH",
    # Meghalaya
    "793": "MEGHALAYA",
    "794": "MEGHALAYA",
    # Manipur
    "795": "MANIPUR",
    # Mizoram (796xxx)
    "796": "MIZORAM",
    # Nagaland
    "797": "NAGALAND",
    # Tripura
    "799": "TRIPURA",
    # Uttarakhand (244-249 range)
    "246": "UTTARAKHAND",
    "247": "UTTAR PRADESH",  # Saharanpur
    "248": "UTTARAKHAND",  # Dehradun
    "249": "UTTARAKHAND",  # Haridwar/Rishikesh
    "262": "UTTAR PRADESH",  # Pilibhit
    "263": "UTTARAKHAND",  # Nainital
    # Jharkhand (814, 815, 825, 826, 827, 828, 829, 831, 832, 833, 834, 835)
    "814": "JHARKHAND",
    "815": "JHARKHAND",
    "825": "JHARKHAND",
    "826": "JHARKHAND",
    "827": "JHARKHAND",
    "828": "JHARKHAND",
    "829": "JHARKHAND",
    "831": "JHARKHAND",
    "832": "JHARKHAND",
    "833": "JHARKHAND",
    "834": "JHARKHAND",
    "835": "JHARKHAND",
    # Chandigarh
    "160": "CHANDIGARH",
}

PIN_2_DIGIT_MAP: dict[str, str] = {
    # 11: Delhi
    "11": "DELHI",
    # 12-13: Haryana
    "12": "HARYANA",
    "13": "HARYANA",
    # 14-15: Punjab
    "14": "PUNJAB",
    "15": "PUNJAB",
    # 16: Punjab / Chandigarh
    "16": "PUNJAB",
    # 17: Himachal Pradesh
    "17": "HIMACHAL PRADESH",
    # 18-19: Jammu & Kashmir / Ladakh
    "18": "JAMMU AND KASHMIR",
    "19": "JAMMU AND KASHMIR",
    # 20-28: Uttar Pradesh
    "20": "UTTAR PRADESH",
    "21": "UTTAR PRADESH",
    "22": "UTTAR PRADESH",
    "23": "UTTAR PRADESH",
    "24": "UTTAR PRADESH",
    "25": "UTTAR PRADESH",
    "26": "UTTAR PRADESH",
    "27": "UTTAR PRADESH",
    "28": "UTTAR PRADESH",
    # 30-34: Rajasthan
    "30": "RAJASTHAN",
    "31": "RAJASTHAN",
    "32": "RAJASTHAN",
    "33": "RAJASTHAN",
    "34": "RAJASTHAN",
    # 36-39: Gujarat
    "36": "GUJARAT",
    "37": "GUJARAT",
    "38": "GUJARAT",
    "39": "GUJARAT",
    # 40-44: Maharashtra
    "40": "MAHARASHTRA",
    "41": "MAHARASHTRA",
    "42": "MAHARASHTRA",
    "43": "MAHARASHTRA",
    "44": "MAHARASHTRA",
    # 45-48: Madhya Pradesh
    "45": "MADHYA PRADESH",
    "46": "MADHYA PRADESH",
    "47": "MADHYA PRADESH",
    "48": "MADHYA PRADESH",
    # 49: Chhattisgarh
    "49": "CHHATTISGARH",
    # 50: Telangana
    "50": "TELANGANA",
    # 51-53: Andhra Pradesh
    "51": "ANDHRA PRADESH",
    "52": "ANDHRA PRADESH",
    "53": "ANDHRA PRADESH",
    # 56-59: Karnataka
    "56": "KARNATAKA",
    "57": "KARNATAKA",
    "58": "KARNATAKA",
    "59": "KARNATAKA",
    # 60-64: Tamil Nadu
    "60": "TAMIL NADU",
    "61": "TAMIL NADU",
    "62": "TAMIL NADU",
    "63": "TAMIL NADU",
    "64": "TAMIL NADU",
    # 67-69: Kerala
    "67": "KERALA",
    "68": "KERALA",
    "69": "KERALA",
    # 70-74: West Bengal
    "70": "WEST BENGAL",
    "71": "WEST BENGAL",
    "72": "WEST BENGAL",
    "73": "WEST BENGAL",
    "74": "WEST BENGAL",
    # 75-77: Odisha
    "75": "ODISHA",
    "76": "ODISHA",
    "77": "ODISHA",
    # 78: Assam
    "78": "ASSAM",
    # 79: North East
    "79": "ASSAM",
    # 80-85: Bihar
    "80": "BIHAR",
    "81": "BIHAR",
    "82": "BIHAR",
    "84": "BIHAR",
    "85": "BIHAR",
}

# -----------------------------------------------------------------------------
# City, District, and Industrial Hub Mapping
# -----------------------------------------------------------------------------
LOCATION_TO_STATE: dict[str, str] = {
    # ----------------- TAMIL NADU -----------------
    "chennai": "TAMIL NADU",
    "madras": "TAMIL NADU",
    "coimbatore": "TAMIL NADU",
    "kovai": "TAMIL NADU",
    "cbe": "TAMIL NADU",
    "madurai": "TAMIL NADU",
    "tiruchirappalli": "TAMIL NADU",
    "trichy": "TAMIL NADU",
    "salem": "TAMIL NADU",
    "tiruppur": "TAMIL NADU",
    "tirupur": "TAMIL NADU",
    "erode": "TAMIL NADU",
    "tirunelveli": "TAMIL NADU",
    "vellore": "TAMIL NADU",
    "thoothukudi": "TAMIL NADU",
    "tuticorin": "TAMIL NADU",
    "dindigul": "TAMIL NADU",
    "thanjavur": "TAMIL NADU",
    "ranipet": "TAMIL NADU",
    "sivakasi": "TAMIL NADU",
    "karur": "TAMIL NADU",
    "ooty": "TAMIL NADU",
    "udhagamandalam": "TAMIL NADU",
    "hosur": "TAMIL NADU",
    "sriperumbudur": "TAMIL NADU",
    "kanchipuram": "TAMIL NADU",
    "chengalpattu": "TAMIL NADU",
    "maraimalai nagar": "TAMIL NADU",
    "oragadam": "TAMIL NADU",
    "ambattur": "TAMIL NADU",
    "guindy": "TAMIL NADU",
    "cuddalore": "TAMIL NADU",
    "nagapattinam": "TAMIL NADU",
    "viluppuram": "TAMIL NADU",
    "kanyakumari": "TAMIL NADU",
    "nagercoil": "TAMIL NADU",
    "ramanathapuram": "TAMIL NADU",
    "virudhunagar": "TAMIL NADU",
    "namakkal": "TAMIL NADU",
    "dharmapuri": "TAMIL NADU",
    "krishnagiri": "TAMIL NADU",
    "pudukkottai": "TAMIL NADU",
    "ariyalur": "TAMIL NADU",
    "perambalur": "TAMIL NADU",
    "thiruvarur": "TAMIL NADU",
    "theni": "TAMIL NADU",
    "tirupathur": "TAMIL NADU",
    "tenkasi": "TAMIL NADU",
    "kallakurichi": "TAMIL NADU",
    "mayiladuthurai": "TAMIL NADU",

    # ----------------- TELANGANA -----------------
    "hyderabad": "TELANGANA",
    "hyd": "TELANGANA",
    "secunderabad": "TELANGANA",
    "cyberabad": "TELANGANA",
    "hitec city": "TELANGANA",
    "gachibowli": "TELANGANA",
    "madhapur": "TELANGANA",
    "kondapur": "TELANGANA",
    "warangal": "TELANGANA",
    "nizamabad": "TELANGANA",
    "karimnagar": "TELANGANA",
    "ramagundam": "TELANGANA",
    "khammam": "TELANGANA",
    "mahbubnagar": "TELANGANA",
    "nalgonda": "TELANGANA",
    "adilabad": "TELANGANA",
    "medchal": "TELANGANA",
    "malkajgiri": "TELANGANA",
    "ranga reddy": "TELANGANA",
    "rangareddy": "TELANGANA",
    "sangareddy": "TELANGANA",
    "siddipet": "TELANGANA",
    "mancherial": "TELANGANA",
    "suryapet": "TELANGANA",
    "jagtial": "TELANGANA",
    "kamareddy": "TELANGANA",
    "kothagudem": "TELANGANA",
    "vikarabad": "TELANGANA",
    "patancheru": "TELANGANA",
    "jeedimetla": "TELANGANA",
    "uppal": "TELANGANA",
    "kukatpally": "TELANGANA",
    "cherlapally": "TELANGANA",

    # ----------------- ANDHRA PRADESH -----------------
    "visakhapatnam": "ANDHRA PRADESH",
    "vizag": "ANDHRA PRADESH",
    "vzg": "ANDHRA PRADESH",
    "waltair": "ANDHRA PRADESH",
    "vijayawada": "ANDHRA PRADESH",
    "bezawada": "ANDHRA PRADESH",
    "bza": "ANDHRA PRADESH",
    "guntur": "ANDHRA PRADESH",
    "gnt": "ANDHRA PRADESH",
    "nellore": "ANDHRA PRADESH",
    "kurnool": "ANDHRA PRADESH",
    "tirupati": "ANDHRA PRADESH",
    "tpt": "ANDHRA PRADESH",
    "kakinada": "ANDHRA PRADESH",
    "rajahmundry": "ANDHRA PRADESH",
    "rajamahendravaram": "ANDHRA PRADESH",
    "kadapa": "ANDHRA PRADESH",
    "anantapur": "ANDHRA PRADESH",
    "anantapuramu": "ANDHRA PRADESH",
    "chittoor": "ANDHRA PRADESH",
    "eluru": "ANDHRA PRADESH",
    "ongole": "ANDHRA PRADESH",
    "srikakulam": "ANDHRA PRADESH",
    "machilipatnam": "ANDHRA PRADESH",
    "sri city": "ANDHRA PRADESH",
    "sricity": "ANDHRA PRADESH",
    "tadepalligudem": "ANDHRA PRADESH",
    "bhimavaram": "ANDHRA PRADESH",
    "mangalagiri": "ANDHRA PRADESH",
    "amaravati": "ANDHRA PRADESH",
    "tenali": "ANDHRA PRADESH",
    "proddatur": "ANDHRA PRADESH",
    "hindupur": "ANDHRA PRADESH",
    "nandyal": "ANDHRA PRADESH",
    "vizianagaram": "ANDHRA PRADESH",

    # ----------------- PUNJAB -----------------
    "ludhiana": "PUNJAB",
    "ldh": "PUNJAB",
    "amritsar": "PUNJAB",
    "asr": "PUNJAB",
    "jalandhar": "PUNJAB",
    "jullundur": "PUNJAB",
    "patiala": "PUNJAB",
    "bathinda": "PUNJAB",
    "bhatinda": "PUNJAB",
    "mohali": "PUNJAB",
    "sas nagar": "PUNJAB",
    "hoshiarpur": "PUNJAB",
    "batala": "PUNJAB",
    "pathankot": "PUNJAB",
    "moga": "PUNJAB",
    "abohar": "PUNJAB",
    "malerkotla": "PUNJAB",
    "khanna": "PUNJAB",
    "phagwara": "PUNJAB",
    "muktsar": "PUNJAB",
    "barnala": "PUNJAB",
    "firozpur": "PUNJAB",
    "ferozepur": "PUNJAB",
    "kapurthala": "PUNJAB",
    "rajpura": "PUNJAB",
    "mansa": "PUNJAB",
    "gurdaspur": "PUNJAB",
    "sangrur": "PUNJAB",
    "fazilka": "PUNJAB",
    "nawanshahr": "PUNJAB",
    "tarn taran": "PUNJAB",
    "derabassi": "PUNJAB",
    "dera bassi": "PUNJAB",

    # ----------------- KERALA -----------------
    "thiruvananthapuram": "KERALA",
    "trivandrum": "KERALA",
    "tvm": "KERALA",
    "kochi": "KERALA",
    "cochin": "KERALA",
    "ernakulam": "KERALA",
    "ekm": "KERALA",
    "kakkanad": "KERALA",
    "infopark": "KERALA",
    "technopark": "KERALA",
    "kozhikode": "KERALA",
    "calicut": "KERALA",
    "clt": "KERALA",
    "kollam": "KERALA",
    "quilon": "KERALA",
    "thrissur": "KERALA",
    "trichur": "KERALA",
    "tcr": "KERALA",
    "palakkad": "KERALA",
    "palghat": "KERALA",
    "alappuzha": "KERALA",
    "alleppey": "KERALA",
    "kannur": "KERALA",
    "cannanore": "KERALA",
    "kottayam": "KERALA",
    "malappuram": "KERALA",
    "kasaragod": "KERALA",
    "wayanad": "KERALA",
    "idukki": "KERALA",
    "pathanamthitta": "KERALA",

    # ----------------- GUJARAT -----------------
    "ahmedabad": "GUJARAT",
    "ahd": "GUJARAT",
    "surat": "GUJARAT",
    "vadodara": "GUJARAT",
    "baroda": "GUJARAT",
    "rajkot": "GUJARAT",
    "bhavnagar": "GUJARAT",
    "jamnagar": "GUJARAT",
    "junagadh": "GUJARAT",
    "gandhinagar": "GUJARAT",
    "anand": "GUJARAT",
    "navsari": "GUJARAT",
    "morbi": "GUJARAT",
    "nadiad": "GUJARAT",
    "surendranagar": "GUJARAT",
    "bharuch": "GUJARAT",
    "mehsana": "GUJARAT",
    "bhuj": "GUJARAT",
    "vapi": "GUJARAT",
    "ankleshwar": "GUJARAT",
    "gandhidham": "GUJARAT",
    "sanand": "GUJARAT",
    "halol": "GUJARAT",
    "porbandar": "GUJARAT",
    "palanpur": "GUJARAT",
    "valsad": "GUJARAT",
    "godhra": "GUJARAT",
    "patan": "GUJARAT",
    "amreli": "GUJARAT",
    "dahej": "GUJARAT",

    # ----------------- RAJASTHAN -----------------
    "jaipur": "RAJASTHAN",
    "jpr": "RAJASTHAN",
    "jodhpur": "RAJASTHAN",
    "kota": "RAJASTHAN",
    "bikaner": "RAJASTHAN",
    "ajmer": "RAJASTHAN",
    "udaipur": "RAJASTHAN",
    "bhilwara": "RAJASTHAN",
    "alwar": "RAJASTHAN",
    "bharatpur": "RAJASTHAN",
    "sikar": "RAJASTHAN",
    "pali": "RAJASTHAN",
    "sri ganganagar": "RAJASTHAN",
    "ganganagar": "RAJASTHAN",
    "neemrana": "RAJASTHAN",
    "bhiwadi": "RAJASTHAN",
    "chittorgarh": "RAJASTHAN",
    "beawar": "RAJASTHAN",
    "jhunjhunu": "RAJASTHAN",
    "churu": "RAJASTHAN",
    "barmer": "RAJASTHAN",
    "kishangarh": "RAJASTHAN",
    "tonk": "RAJASTHAN",
    "hanumangarh": "RAJASTHAN",
    "dholpur": "RAJASTHAN",
    "sawai madhopur": "RAJASTHAN",
    "nagaur": "RAJASTHAN",
    "jaisalmer": "RAJASTHAN",
    "bundi": "RAJASTHAN",

    # ----------------- ODISHA -----------------
    "bhubaneswar": "ODISHA",
    "bbsr": "ODISHA",
    "cuttack": "ODISHA",
    "ctc": "ODISHA",
    "rourkela": "ODISHA",
    "berhampur": "ODISHA",
    "sambalpur": "ODISHA",
    "puri": "ODISHA",
    "balasore": "ODISHA",
    "bhadrak": "ODISHA",
    "baripada": "ODISHA",
    "jharsuguda": "ODISHA",
    "angul": "ODISHA",
    "paradeep": "ODISHA",
    "dhenkanal": "ODISHA",
    "jeypore": "ODISHA",
    "rayagada": "ODISHA",
    "khordha": "ODISHA",
    "khurda": "ODISHA",
    "kendujhar": "ODISHA",
    "keonjhar": "ODISHA",
    "balangir": "ODISHA",
    "kalinga nagar": "ODISHA",
    "kalinganagar": "ODISHA",

    # ----------------- WEST BENGAL -----------------
    "kolkata": "WEST BENGAL",
    "calcutta": "WEST BENGAL",
    "ccu": "WEST BENGAL",
    "howrah": "WEST BENGAL",
    "durgapur": "WEST BENGAL",
    "asansol": "WEST BENGAL",
    "siliguri": "WEST BENGAL",
    "bardhaman": "WEST BENGAL",
    "burdwan": "WEST BENGAL",
    "malda": "WEST BENGAL",
    "kharagpur": "WEST BENGAL",
    "haldia": "WEST BENGAL",
    "darjeeling": "WEST BENGAL",
    "jalpaiguri": "WEST BENGAL",
    "salt lake": "WEST BENGAL",
    "new town": "WEST BENGAL",
    "hooghly": "WEST BENGAL",
    "chinsurah": "WEST BENGAL",
    "chandannagar": "WEST BENGAL",
    "serampore": "WEST BENGAL",
    "kalyani": "WEST BENGAL",
    "barasat": "WEST BENGAL",
    "raiganj": "WEST BENGAL",
    "krishnanagar": "WEST BENGAL",
    "berhampore": "WEST BENGAL",
    "bankura": "WEST BENGAL",
    "purulia": "WEST BENGAL",
    "alipurduar": "WEST BENGAL",
    "cooch behar": "WEST BENGAL",

    # ----------------- UTTAR PRADESH -----------------
    "lucknow": "UTTAR PRADESH",
    "lko": "UTTAR PRADESH",
    "kanpur": "UTTAR PRADESH",
    "knp": "UTTAR PRADESH",
    "ghaziabad": "UTTAR PRADESH",
    "noida": "UTTAR PRADESH",
    "greater noida": "UTTAR PRADESH",
    "agra": "UTTAR PRADESH",
    "varanasi": "UTTAR PRADESH",
    "benares": "UTTAR PRADESH",
    "banaras": "UTTAR PRADESH",
    "kashi": "UTTAR PRADESH",
    "meerut": "UTTAR PRADESH",
    "prayagraj": "UTTAR PRADESH",
    "allahabad": "UTTAR PRADESH",
    "bareilly": "UTTAR PRADESH",
    "aligarh": "UTTAR PRADESH",
    "moradabad": "UTTAR PRADESH",
    "saharanpur": "UTTAR PRADESH",
    "gorakhpur": "UTTAR PRADESH",
    "firozabad": "UTTAR PRADESH",
    "jhansi": "UTTAR PRADESH",
    "muzaffarnagar": "UTTAR PRADESH",
    "mathura": "UTTAR PRADESH",
    "ayodhya": "UTTAR PRADESH",
    "faizabad": "UTTAR PRADESH",
    "budaun": "UTTAR PRADESH",
    "rampur": "UTTAR PRADESH",
    "shahjahanpur": "UTTAR PRADESH",
    "etawah": "UTTAR PRADESH",
    "mirzapur": "UTTAR PRADESH",
    "bulandshahr": "UTTAR PRADESH",
    "sambhal": "UTTAR PRADESH",
    "amroha": "UTTAR PRADESH",
    "hardoi": "UTTAR PRADESH",
    "fatehpur": "UTTAR PRADESH",
    "raebareli": "UTTAR PRADESH",
    "orai": "UTTAR PRADESH",
    "sitapur": "UTTAR PRADESH",
    "bahraich": "UTTAR PRADESH",
    "modinagar": "UTTAR PRADESH",
    "hapur": "UTTAR PRADESH",

    # ----------------- BIHAR -----------------
    "patna": "BIHAR",
    "pat": "BIHAR",
    "gaya": "BIHAR",
    "bhagalpur": "BIHAR",
    "muzaffarpur": "BIHAR",
    "purnia": "BIHAR",
    "purnea": "BIHAR",
    "darbhanga": "BIHAR",
    "bihar sharif": "BIHAR",
    "arrah": "BIHAR",
    "ara": "BIHAR",
    "begusarai": "BIHAR",
    "katihar": "BIHAR",
    "munger": "BIHAR",
    "monghyr": "BIHAR",
    "chhapra": "BIHAR",
    "chapra": "BIHAR",
    "danapur": "BIHAR",
    "bettiah": "BIHAR",
    "saharsa": "BIHAR",
    "sasaram": "BIHAR",
    "hajipur": "BIHAR",
    "dehri": "BIHAR",
    "siwan": "BIHAR",
    "motihari": "BIHAR",
    "nawada": "BIHAR",
    "bagaha": "BIHAR",
    "buxar": "BIHAR",
    "kishanganj": "BIHAR",
    "sitamarhi": "BIHAR",
    "jamalpur": "BIHAR",
    "jehanabad": "BIHAR",
    "madhubani": "BIHAR",
    "samastipur": "BIHAR",
    "khagaria": "BIHAR",
    "gopalganj": "BIHAR",
    "araria": "BIHAR",

    # ----------------- MIZORAM -----------------
    "aizawl": "MIZORAM",
    "lunglei": "MIZORAM",
    "champhai": "MIZORAM",
    "serchhip": "MIZORAM",
    "kolasib": "MIZORAM",
    "lawngtlai": "MIZORAM",
    "saitual": "MIZORAM",
    "mamit": "MIZORAM",
    "khawzawl": "MIZORAM",
    "hnahthial": "MIZORAM",

    # ----------------- PUDUCHERRY -----------------
    "puducherry": "PUDUCHERRY",
    "pondicherry": "PUDUCHERRY",
    "karaikal": "PUDUCHERRY",
    "mahe": "PUDUCHERRY",
    "yanam": "PUDUCHERRY",

    # ----------------- UNSUPPORTED STATES (Major Hubs) -----------------
    # Karnataka
    "bengaluru": "KARNATAKA",
    "bangalore": "KARNATAKA",
    "blr": "KARNATAKA",
    "whitefield": "KARNATAKA",
    "electronic city": "KARNATAKA",
    "mysuru": "KARNATAKA",
    "mysore": "KARNATAKA",
    "mangaluru": "KARNATAKA",
    "mangalore": "KARNATAKA",
    "hubballi": "KARNATAKA",
    "hubli": "KARNATAKA",
    "belagavi": "KARNATAKA",
    "belgaum": "KARNATAKA",
    "gulbarga": "KARNATAKA",
    "kalaburagi": "KARNATAKA",
    "davangere": "KARNATAKA",
    "bellary": "KARNATAKA",
    "ballari": "KARNATAKA",
    "shimoga": "KARNATAKA",
    "shivamogga": "KARNATAKA",
    "tumkur": "KARNATAKA",
    "tumakuru": "KARNATAKA",
    "udupi": "KARNATAKA",
    # Maharashtra
    "mumbai": "MAHARASHTRA",
    "bombay": "MAHARASHTRA",
    "bom": "MAHARASHTRA",
    "pune": "MAHARASHTRA",
    "poona": "MAHARASHTRA",
    "nagpur": "MAHARASHTRA",
    "nashik": "MAHARASHTRA",
    "nasik": "MAHARASHTRA",
    "thane": "MAHARASHTRA",
    "navi mumbai": "MAHARASHTRA",
    "solapur": "MAHARASHTRA",
    "amravati": "MAHARASHTRA",
    "kolhapur": "MAHARASHTRA",
    "sangli": "MAHARASHTRA",
    "jalgaon": "MAHARASHTRA",
    "akola": "MAHARASHTRA",
    "latur": "MAHARASHTRA",
    "dhule": "MAHARASHTRA",
    "ahmednagar": "MAHARASHTRA",
    "chandrapur": "MAHARASHTRA",
    "parbhani": "MAHARASHTRA",
    # Delhi
    "delhi": "DELHI",
    "new delhi": "DELHI",
    "del": "DELHI",
    "connaught place": "DELHI",
    "okhla": "DELHI",
    "nehru place": "DELHI",
    # Haryana
    "gurgaon": "HARYANA",
    "gurugram": "HARYANA",
    "ggn": "HARYANA",
    "faridabad": "HARYANA",
    "panipat": "HARYANA",
    "ambala": "HARYANA",
    "rohtak": "HARYANA",
    "hisar": "HARYANA",
    "karnal": "HARYANA",
    "sonipat": "HARYANA",
    "panchkula": "HARYANA",
    "bhiwani": "HARYANA",
    "manesar": "HARYANA",
    "bahadurgarh": "HARYANA",
    # Madhya Pradesh
    "indore": "MADHYA PRADESH",
    "bhopal": "MADHYA PRADESH",
    "jabalpur": "MADHYA PRADESH",
    "gwalior": "MADHYA PRADESH",
    "ujjain": "MADHYA PRADESH",
    "sagar": "MADHYA PRADESH",
    "dewas": "MADHYA PRADESH",
    "satna": "MADHYA PRADESH",
    "ratlam": "MADHYA PRADESH",
    "rewa": "MADHYA PRADESH",
    # Jharkhand
    "ranchi": "JHARKHAND",
    "jamshedpur": "JHARKHAND",
    "tatanagar": "JHARKHAND",
    "dhanbad": "JHARKHAND",
    "bokaro": "JHARKHAND",
    "deoghar": "JHARKHAND",
    "hazaribagh": "JHARKHAND",
    # Chhattisgarh
    "raipur": "CHHATTISGARH",
    "bhilai": "CHHATTISGARH",
    "durg": "CHHATTISGARH",
    "korba": "CHHATTISGARH",
    "rajnandgaon": "CHHATTISGARH",
    # Assam
    "guwahati": "ASSAM",
    "gauhati": "ASSAM",
    "silchar": "ASSAM",
    "dibrugarh": "ASSAM",
    "jorhat": "ASSAM",
    "nagaon": "ASSAM",
    "tinsukia": "ASSAM",
    "tezpur": "ASSAM",
    # Uttarakhand
    "dehradun": "UTTARAKHAND",
    "haridwar": "UTTARAKHAND",
    "rishikesh": "UTTARAKHAND",
    "roorkee": "UTTARAKHAND",
    "haldwani": "UTTARAKHAND",
    "rudrapur": "UTTARAKHAND",
    "nainital": "UTTARAKHAND",
    # Himachal Pradesh
    "shimla": "HIMACHAL PRADESH",
    "simla": "HIMACHAL PRADESH",
    "dharamshala": "HIMACHAL PRADESH",
    "solan": "HIMACHAL PRADESH",
    "mandi": "HIMACHAL PRADESH",
    "baddi": "HIMACHAL PRADESH",
    "kullu": "HIMACHAL PRADESH",
    "manali": "HIMACHAL PRADESH",
    # Goa
    "panaji": "GOA",
    "panjim": "GOA",
    "margao": "GOA",
    "vasco": "GOA",
    "mapusa": "GOA",
    "ponda": "GOA",
    # Chandigarh
    "chandigarh": "CHANDIGARH",
    "chd": "CHANDIGARH",
}

# Ambiguous place names in India that belong to multiple states
AMBIGUOUS_LOCATIONS: dict[str, list[str]] = {
    "bilaspur": ["CHHATTISGARH", "HIMACHAL PRADESH"],
    "aurangabad": ["MAHARASHTRA", "BIHAR"],
    "hamirpur": ["UTTAR PRADESH", "HIMACHAL PRADESH"],
    "pratapgarh": ["UTTAR PRADESH", "RAJASTHAN"],
    "balrampur": ["UTTAR PRADESH", "CHHATTISGARH"],
    "rampur": ["UTTAR PRADESH", "HIMACHAL PRADESH"],
}


@dataclass
class LocationDetectionResult:
    raw_location: str
    detected_state: str | None
    status: str  # "IDENTIFIED" | "UNSUPPORTED_STATE" | "AMBIGUOUS" | "UNRESOLVED" | "INSUFFICIENT_INPUT"
    is_supported: bool
    confidence: str  # "HIGH" | "MEDIUM" | "LOW" | "NONE"
    matched_keyword: str | None
    candidate_states: list[str]
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_location_text(text: str) -> str:
    """Clean location text by removing punctuation and excess whitespace."""
    if not text:
        return ""
    # Replace non-alphanumeric (except commas, hyphens, and spaces) with spaces
    cleaned = re.sub(r"[^\w\s,\-]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def detect_state_from_pincode(pincode_str: str) -> str | None:
    """Determine state from a 6-digit Indian PIN code."""
    if not pincode_str or len(pincode_str) != 6 or not pincode_str.isdigit():
        return None
    # Check 3-digit prefix first
    prefix_3 = pincode_str[:3]
    if prefix_3 in PIN_3_DIGIT_MAP:
        return PIN_3_DIGIT_MAP[prefix_3]
    # Check 2-digit prefix
    prefix_2 = pincode_str[:2]
    if prefix_2 in PIN_2_DIGIT_MAP:
        return PIN_2_DIGIT_MAP[prefix_2]
    return None


def detect_work_state(raw_location: str | None) -> LocationDetectionResult:
    """Automatically detect Indian State from free-text place of work."""
    if not raw_location or not raw_location.strip():
        return LocationDetectionResult(
            raw_location=raw_location or "",
            detected_state=None,
            status="INSUFFICIENT_INPUT",
            is_supported=False,
            confidence="NONE",
            matched_keyword=None,
            candidate_states=[],
            message="No location entered.",
        )

    norm_text = normalize_location_text(raw_location)
    if len(norm_text) < 2:
        return LocationDetectionResult(
            raw_location=raw_location,
            detected_state=None,
            status="INSUFFICIENT_INPUT",
            is_supported=False,
            confidence="NONE",
            matched_keyword=None,
            candidate_states=[],
            message="Location text is too short to identify state.",
        )

    # 1. Check for 6-digit Indian PIN code
    pin_match = re.search(r"\b([1-9][0-9]{5})\b", norm_text)
    if pin_match:
        pin = pin_match.group(1)
        pin_state = detect_state_from_pincode(pin)
        if pin_state:
            is_supp = pin_state in SUPPORTED_13_STATES
            status = "IDENTIFIED" if is_supp else "UNSUPPORTED_STATE"
            msg = (
                f"Identified {pin_state.title()} from PIN code {pin}."
                if is_supp
                else f"Identified {pin_state.title()} from PIN code {pin}, but this state is not in the semi-skilled wage register."
            )
            return LocationDetectionResult(
                raw_location=raw_location,
                detected_state=pin_state,
                status=status,
                is_supported=is_supp,
                confidence="HIGH",
                matched_keyword=pin,
                candidate_states=[pin_state],
                message=msg,
            )

    # 2. Check for explicit state mention in text
    lower_norm = norm_text.lower()
    
    # Check canonical states & aliases in STATE_ALIASES and NON_13_STATE_ALIASES
    all_aliases = dict(NON_13_STATE_ALIASES)
    all_aliases.update(STATE_ALIASES)

    # Sort aliases by descending length so "tamil nadu" matches before "tamil" or "tn"
    sorted_aliases = sorted(all_aliases.items(), key=lambda item: len(item[0]), reverse=True)
    for alias, canonical in sorted_aliases:
        # Check whole word match
        pattern = r"\b" + re.escape(alias) + r"\b"
        if re.search(pattern, lower_norm):
            is_supp = canonical in SUPPORTED_13_STATES
            status = "IDENTIFIED" if is_supp else "UNSUPPORTED_STATE"
            msg = (
                f"Identified state: {canonical.title()}."
                if is_supp
                else f"State '{canonical.title()}' is not in the statutory 13-state minimum wage register."
            )
            return LocationDetectionResult(
                raw_location=raw_location,
                detected_state=canonical,
                status=status,
                is_supported=is_supp,
                confidence="HIGH",
                matched_keyword=alias,
                candidate_states=[canonical],
                message=msg,
            )

    # 3. Check for Ambiguous Location names
    # Split text into comma-separated parts or tokens
    tokens = [t.strip().lower() for t in re.split(r"[,/;\-]+", norm_text) if t.strip()]
    for token in tokens:
        if token in AMBIGUOUS_LOCATIONS:
            candidates = AMBIGUOUS_LOCATIONS[token]
            return LocationDetectionResult(
                raw_location=raw_location,
                detected_state=None,
                status="AMBIGUOUS",
                is_supported=False,
                confidence="LOW",
                matched_keyword=token,
                candidate_states=candidates,
                message=f"Location '{token.title()}' is ambiguous and could refer to: {', '.join(s.title() for s in candidates)}. Please specify district or state.",
            )

    # 4. Check City / District dictionary
    # Search by multi-word segments first, then individual words
    # Check direct segment match
    for token in tokens:
        if token in LOCATION_TO_STATE:
            state = LOCATION_TO_STATE[token]
            is_supp = state in SUPPORTED_13_STATES
            status = "IDENTIFIED" if is_supp else "UNSUPPORTED_STATE"
            msg = (
                f"Identified {state.title()} from city/location '{token.title()}'."
                if is_supp
                else f"Identified {state.title()} from '{token.title()}', but this state is not in the minimum wage register."
            )
            return LocationDetectionResult(
                raw_location=raw_location,
                detected_state=state,
                status=status,
                is_supported=is_supp,
                confidence="HIGH",
                matched_keyword=token,
                candidate_states=[state],
                message=msg,
            )

    # Check substring / word search in text for known city/district keys
    sorted_places = sorted(LOCATION_TO_STATE.items(), key=lambda item: len(item[0]), reverse=True)
    for place_name, state in sorted_places:
        # Word boundary match
        pattern = r"\b" + re.escape(place_name) + r"\b"
        if re.search(pattern, lower_norm):
            is_supp = state in SUPPORTED_13_STATES
            status = "IDENTIFIED" if is_supp else "UNSUPPORTED_STATE"
            msg = (
                f"Identified {state.title()} from '{place_name.title()}'."
                if is_supp
                else f"Identified {state.title()} from '{place_name.title()}', but this state is not in the minimum wage register."
            )
            return LocationDetectionResult(
                raw_location=raw_location,
                detected_state=state,
                status=status,
                is_supported=is_supp,
                confidence="HIGH",
                matched_keyword=place_name,
                candidate_states=[state],
                message=msg,
            )

    # 5. Could not resolve
    return LocationDetectionResult(
        raw_location=raw_location,
        detected_state=None,
        status="UNRESOLVED",
        is_supported=False,
        confidence="NONE",
        matched_keyword=None,
        candidate_states=[],
        message=f"Could not identify Indian state from '{raw_location}'. Please provide a recognized city or state.",
    )

