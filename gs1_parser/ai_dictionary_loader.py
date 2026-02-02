"""
AI Dictionary Loader for GS1 Parser

Loads and manages the GS1 Application Identifier dictionary.
Based on GS1 Barcode Syntax Dictionary specification.

Reference: https://ref.gs1.org/tools/gs1-barcode-syntax-resource/syntax-dictionary/
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set


@dataclass
class AIEntry:
    """
    Represents a single GS1 Application Identifier entry.
    
    Attributes:
        ai: The Application Identifier code (2-4 digits)
        title: Human-readable title/name
        fixed_length: Fixed data length if predefined, None if variable
        max_length: Maximum data length for variable-length AIs
        min_length: Minimum data length
        data_type: 'N' for numeric, 'X' for alphanumeric, 'Y' for ISO chars
        separator_required: True if FNC1/GS required after this field (not fixed-length)
        regex: Validation regex pattern
        check_digit: True if field contains a check digit
        decimal_positions: Number of implied decimal positions (for weight/measure AIs)
        date_format: Date format if applicable ('YYMMDD', 'YYMMD0', 'YYYYMMDD')
        required_ais: List of AIs that must be present with this AI
        exclusive_ais: List of AIs that cannot be present with this AI
        components: List of component specifications
    """
    ai: str
    title: str
    fixed_length: Optional[int] = None
    max_length: int = 0
    min_length: int = 0
    data_type: str = "X"  # 'N' = numeric, 'X' = alphanumeric
    separator_required: bool = True
    regex: Optional[str] = None
    check_digit: bool = False
    decimal_positions: Optional[int] = None
    date_format: Optional[str] = None
    required_ais: List[str] = field(default_factory=list)
    exclusive_ais: List[str] = field(default_factory=list)
    components: List[dict] = field(default_factory=list)
    is_dlp_key: bool = False  # GS1 Digital Link primary key


class TrieNode:
    """Trie node for efficient AI prefix matching."""
    __slots__ = ['children', 'ai_entry', 'is_end']
    
    def __init__(self):
        self.children: Dict[str, TrieNode] = {}
        self.ai_entry: Optional[AIEntry] = None
        self.is_end: bool = False


class AITrie:
    """
    Trie data structure for O(k) AI lookup where k is AI length (2-4).
    Supports longest-prefix matching for efficient parsing.
    """
    
    def __init__(self):
        self.root = TrieNode()
        self._all_ais: Dict[str, AIEntry] = {}
    
    def insert(self, ai: str, entry: AIEntry) -> None:
        """Insert an AI entry into the trie."""
        node = self.root
        for char in ai:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
        node.is_end = True
        node.ai_entry = entry
        self._all_ais[ai] = entry
    
    def find_longest_match(self, text: str, start: int = 0) -> Tuple[Optional[AIEntry], int]:
        """
        Find the longest matching AI starting at position 'start'.
        Returns (AIEntry, length) or (None, 0) if no match.
        Uses longest-match strategy: 4 -> 3 -> 2 digit AIs.
        """
        node = self.root
        last_match: Optional[AIEntry] = None
        last_match_len = 0
        
        for i, char in enumerate(text[start:start + 4]):  # Max AI length is 4
            if char not in node.children:
                break
            node = node.children[char]
            if node.is_end:
                last_match = node.ai_entry
                last_match_len = i + 1
        
        return last_match, last_match_len
    
    def get(self, ai: str) -> Optional[AIEntry]:
        """Get AI entry by exact AI code."""
        return self._all_ais.get(ai)
    
    def __contains__(self, ai: str) -> bool:
        return ai in self._all_ais
    
    def __len__(self) -> int:
        return len(self._all_ais)
    
    def all_entries(self) -> Dict[str, AIEntry]:
        """Return all AI entries."""
        return self._all_ais.copy()


# GS1 AI encodable character set 82 (for alphanumeric data)
CSET82 = set(
    '!"#$%&\'()*+,-./0123456789:;<=>?@'
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`'
    'abcdefghijklmnopqrstuvwxyz{|}'
)

# GS1 AI encodable character set 39 (for restricted alphanumeric)
CSET39 = set('#-/0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')


def _parse_syntax_spec(spec: str) -> Tuple[str, int, int, List[str]]:
    """
    Parse GS1 Syntax Dictionary specification format.
    
    Examples:
        "N14" -> ('N', 14, 14, [])
        "X..20" -> ('X', 1, 20, [])
        "N6,yymmd0" -> ('N', 6, 6, ['yymmd0'])
        "N14,csum,key" -> ('N', 14, 14, ['csum', 'key'])
    
    Returns:
        (data_type, min_length, max_length, linters)
    """
    parts = spec.split(',')
    type_len = parts[0]
    linters = parts[1:] if len(parts) > 1 else []
    
    # Parse type and length
    data_type = type_len[0]
    len_spec = type_len[1:]
    
    if '..' in len_spec:
        # Variable length: "..20" means 1-20
        min_len, max_len = 1, int(len_spec.replace('..', ''))
    elif len_spec:
        # Fixed length
        min_len = max_len = int(len_spec)
    else:
        min_len = max_len = 0
    
    return data_type, min_len, max_len, linters


def _build_regex_for_ai(entry: AIEntry) -> str:
    """Build validation regex based on AI specification."""
    if entry.data_type == 'N':
        if entry.fixed_length:
            return f'^\\d{{{entry.fixed_length}}}$'
        else:
            return f'^\\d{{{entry.min_length},{entry.max_length}}}$'
    else:  # Alphanumeric
        # Use GS1 character set 82
        if entry.fixed_length:
            return f'^[!-z]{{{entry.fixed_length}}}$'
        else:
            return f'^[!-z]{{{entry.min_length},{entry.max_length}}}$'


# Comprehensive GS1 AI Dictionary
# Based on GS1 Barcode Syntax Dictionary and GS1 General Specifications
# Reference: https://ref.gs1.org/ai/
RAW_AI_DICTIONARY = """
# AI    Flags  Specification                     Attributes                                         Title
00         *   N18,csum,gcppos2                  dlpkey                                             # SSCC
01         *   N14,csum,gcppos2                  ex=255,37 dlpkey=22,10,21|235                      # GTIN
02         *   N14,csum,gcppos2                  ex=01,03 req=37                                    # CONTENT
10             X..20                             req=01,02,03,8006,8026                             # BATCH/LOT
11         *   N6,yymmd0                         req=01,02,03,8006,8026                             # PROD DATE
12         *   N6,yymmd0                         req=8020                                           # DUE DATE
13         *   N6,yymmd0                         req=01,02,03,8006,8026                             # PACK DATE
15         *   N6,yymmd0                         req=01,02,03,8006,8026                             # BEST BEFORE or BEST BY
16         *   N6,yymmd0                         req=01,02,03,8006,8026                             # SELL BY
17         *   N6,yymmd0                         req=01,02,03,8006,8026                             # USE BY or EXPIRY
20         *   N2                                req=01,02                                          # VARIANT
21             X..20                             req=01,8006                                        # SERIAL
22             X..20                             req=01                                             # CPV
235            X..28                             req=01 ex=21                                       # TPX
240            X..30                             req=01,02                                          # ADDITIONAL ID
241            X..30                             req=01,02                                          # CUST. PART No.
242            N..6                              req=01                                             # MTO VARIANT
243            X..20                             req=01                                             # PCN
250            X..30                             req=01                                             # SECONDARY SERIAL
251            X..30                             req=01                                             # REF. TO SOURCE
253            N13,csum,key X..17                dlpkey                                             # GDTI
254            X..20                             req=414,417                                        # GLN EXTENSION COMPONENT
255            N13,csum,key N..12                ex=01,02 dlpkey                                    # GCN
30             N..8                              req=01,02                                          # VAR. COUNT
310n       *   N6                                req=01,02 ex=320n                                  # NET WEIGHT (kg)
311n       *   N6                                req=01,02 ex=321n                                  # LENGTH (m)
312n       *   N6                                req=01,02 ex=322n                                  # WIDTH (m)
313n       *   N6                                req=01,02 ex=323n                                  # HEIGHT (m)
314n       *   N6                                req=01,02 ex=324n                                  # AREA (m²)
315n       *   N6                                req=01,02 ex=316n                                  # NET VOLUME (l)
316n       *   N6                                req=01,02 ex=315n                                  # NET VOLUME (m³)
320n       *   N6                                req=01,02 ex=310n                                  # NET WEIGHT (lb)
321n       *   N6                                req=01,02 ex=311n                                  # LENGTH (in)
322n       *   N6                                req=01,02 ex=312n                                  # LENGTH (ft)
323n       *   N6                                req=01,02 ex=313n                                  # LENGTH (yd)
324n       *   N6                                req=01,02 ex=314n                                  # WIDTH (in)
325n       *   N6                                req=01,02                                          # WIDTH (ft)
326n       *   N6                                req=01,02                                          # WIDTH (yd)
327n       *   N6                                req=01,02                                          # HEIGHT (in)
328n       *   N6                                req=01,02                                          # HEIGHT (ft)
329n       *   N6                                req=01,02                                          # HEIGHT (yd)
330n       *   N6                                req=00                                             # GROSS WEIGHT (kg)
331n       *   N6                                req=00                                             # LENGTH (m), log
332n       *   N6                                req=00                                             # WIDTH (m), log
333n       *   N6                                req=00                                             # HEIGHT (m), log
334n       *   N6                                req=00                                             # AREA (m²), log
335n       *   N6                                req=00                                             # VOLUME (l), log
336n       *   N6                                req=00                                             # VOLUME (m³), log
337n       *   N6                                req=00                                             # KG PER m²
340n       *   N6                                req=00                                             # GROSS WEIGHT (lb)
341n       *   N6                                req=00                                             # LENGTH (in), log
342n       *   N6                                req=00                                             # LENGTH (ft), log
343n       *   N6                                req=00                                             # LENGTH (yd), log
344n       *   N6                                req=00                                             # WIDTH (in), log
345n       *   N6                                req=00                                             # WIDTH (ft), log
346n       *   N6                                req=00                                             # WIDTH (yd), log
347n       *   N6                                req=00                                             # HEIGHT (in), log
348n       *   N6                                req=00                                             # HEIGHT (ft), log
349n       *   N6                                req=00                                             # HEIGHT (yd), log
350n       *   N6                                req=00                                             # AREA (in²)
351n       *   N6                                req=00                                             # AREA (ft²)
352n       *   N6                                req=00                                             # AREA (yd²)
353n       *   N6                                req=00                                             # AREA (in²), log
354n       *   N6                                req=00                                             # AREA (ft²), log
355n       *   N6                                req=00                                             # AREA (yd²), log
356n       *   N6                                req=01,02                                          # NET WEIGHT (t oz)
357n       *   N6                                req=01,02                                          # NET VOLUME (oz)
360n       *   N6                                req=00                                             # NET VOLUME (q)
361n       *   N6                                req=00                                             # NET VOLUME (gal)
362n       *   N6                                req=00                                             # VOLUME (q), log
363n       *   N6                                req=00                                             # VOLUME (gal), log
364n       *   N6                                req=00                                             # VOLUME (in³)
365n       *   N6                                req=00                                             # VOLUME (ft³)
366n       *   N6                                req=00                                             # VOLUME (yd³)
367n       *   N6                                req=00                                             # VOLUME (in³), log
368n       *   N6                                req=00                                             # VOLUME (ft³), log
369n       *   N6                                req=00                                             # VOLUME (yd³), log
37             N..8                              req=02                                             # COUNT
390n           N..15                             req=8020 ex=391n,394n,8111                         # AMOUNT
391n           N3,iso4217 N..15                  req=8020 ex=390n,394n,8111                         # AMOUNT
392n           N..15                             req=01,02                                          # PRICE
393n           N3,iso4217 N..15                  req=01,02                                          # PRICE
394n           N4 N..15                          req=8020 ex=390n,391n,8111                         # PRCNT OFF
395n           N6                                req=01,02                                          # PRICE/UoM
400            X..30                                                                                # ORDER NUMBER
401            X..30,csumalpha,key               dlpkey                                             # GINC
402            N17,csum,key                      dlpkey                                             # GSIN
403            X..30                             req=00                                             # ROUTE
410        *   N13,csum,key                                                                         # SHIP TO LOC
411        *   N13,csum,key                                                                         # BILL TO
412        *   N13,csum,key                                                                         # PURCHASE FROM
413        *   N13,csum,key                                                                         # SHIP FOR LOC
414        *   N13,csum,key                      dlpkey=254                                         # LOC No.
415        *   N13,csum,key                      dlpkey                                             # PAY TO
416        *   N13,csum,key                                                                         # PROD/SERV LOC
417        *   N13,csum,key                      dlpkey=7040                                        # PARTY
420            X..20                                                                                # SHIP TO POST
421            N3,iso3166 X..9                                                                      # SHIP TO POST
422        *   N3,iso3166                        req=01,02                                          # ORIGIN
423            N..15,iso3166list                 req=01,02                                          # COUNTRY - INITIAL PROCESS
424        *   N3,iso3166                        req=01,02                                          # COUNTRY - PROCESS
425            N..15,iso3166list                 req=01,02                                          # COUNTRY - DISASSEMBLY
426        *   N3,iso3166                        req=01,02                                          # COUNTRY - FULL PROCESS
427            X..3                              req=01,02                                          # ORIGIN SUBDIVISION
4300           X..35,pcenc                                                                          # SHIP TO COMP
4301           X..35,pcenc                                                                          # SHIP TO NAME
4302           X..70,pcenc                                                                          # SHIP TO ADD1
4303           X..70,pcenc                                                                          # SHIP TO ADD2
4304           X..70,pcenc                                                                          # SHIP TO SUB
4305           X..70,pcenc                                                                          # SHIP TO LOC
4306           X..70,pcenc                                                                          # SHIP TO REG
4307           X2,iso3166alpha2                                                                     # SHIP TO COUNTRY
4308           X..30                                                                                # SHIP TO PHONE
4309           N20,latlong                                                                          # SHIP TO GEO
4310           X..35,pcenc                                                                          # RTN TO COMP
4311           X..35,pcenc                                                                          # RTN TO NAME
4312           X..70,pcenc                                                                          # RTN TO ADD1
4313           X..70,pcenc                                                                          # RTN TO ADD2
4314           X..70,pcenc                                                                          # RTN TO SUB
4315           X..70,pcenc                                                                          # RTN TO LOC
4316           X..70,pcenc                                                                          # RTN TO REG
4317           X2,iso3166alpha2                                                                     # RTN TO COUNTRY
4318           X..30                                                                                # RTN TO POST
4319           X..30                                                                                # RTN TO PHONE
4320           X..35,pcenc                                                                          # SRV DESCRIPTION
4321           N1,yesno                                                                             # DANGEROUS GOODS
4322           N1,yesno                                                                             # AUTH LEAVE
4323           N1,yesno                                                                             # SIG REQUIRED
4324           N10,yymmddhh                                                                         # NBEF DEL DT
4325           N10,yymmddhh                                                                         # NAFT DEL DT
4326           N6,yymmdd                                                                            # REL DATE
4330           X..35,pcenc                       req=01,02                                          # MAX TEMP (F)
4331           X..35,pcenc                       req=01,02                                          # MAX TEMP (C)
4332           X..35,pcenc                       req=01,02                                          # MIN TEMP (F)
4333           X..35,pcenc                       req=01,02                                          # MIN TEMP (C)
7001       *   N13                               req=01,02                                          # NSN
7002           X..30                             req=01,02                                          # MEAT CUT
7003       *   N10,yymmddhh                      req=01,02                                          # EXPIRY TIME
7004           N..4                              req=01,02                                          # ACTIVE POTENCY
7005           X..12                             req=01,02                                          # CATCH AREA
7006       *   N6,yymmdd                         req=01,02                                          # FIRST FREEZE DATE
7007           N6,yymmdd N..6,yymmdd             req=01,02                                          # HARVEST DATE
7008           X..3                              req=01,02                                          # AQUATIC SPECIES
7009           X..10                             req=01,02                                          # FISHING GEAR TYPE
7010           X..2                              req=01,02                                          # PROD METHOD
7011           N6,yymmdd N..4,hhmm               req=01,02                                          # TEST BY DATE
7020           X..20                             req=01,414                                         # REFURB LOT
7021           X..20                             req=01                                             # FUNC STAT
7022           X..20                             req=01                                             # REV STAT
7023           X..30                             req=00,01                                          # GIAI - ASSEMBLY
7030           N3,iso3166999 X..27               req=01                                             # PROCESSOR # 0
7031           N3,iso3166999 X..27               req=01                                             # PROCESSOR # 1
7032           N3,iso3166999 X..27               req=01                                             # PROCESSOR # 2
7033           N3,iso3166999 X..27               req=01                                             # PROCESSOR # 3
7034           N3,iso3166999 X..27               req=01                                             # PROCESSOR # 4
7035           N3,iso3166999 X..27               req=01                                             # PROCESSOR # 5
7036           N3,iso3166999 X..27               req=01                                             # PROCESSOR # 6
7037           N3,iso3166999 X..27               req=01                                             # PROCESSOR # 7
7038           N3,iso3166999 X..27               req=01                                             # PROCESSOR # 8
7039           N3,iso3166999 X..27               req=01                                             # PROCESSOR # 9
7040           N1 X1 X1 X1,importeridx           req=417                                            # UIC+EXT
710            X..20                             req=01                                             # NHRN PZN
711            X..20                             req=01                                             # NHRN CIP
712            X..20                             req=01                                             # NHRN CN
713            X..20                             req=01                                             # NHRN DRN
714            X..20                             req=01                                             # NHRN AIM
715            X..20                             req=01                                             # NHRN NDC
716            X..20                             req=01                                             # NHRN AIC
717            X..20                             req=01                                             # NHRN SRN
7230           X2 X..28                          req=01,8004                                        # CERT # 1
7231           X2 X..28                          req=01,8004                                        # CERT # 2
7232           X2 X..28                          req=01,8004                                        # CERT # 3
7233           X2 X..28                          req=01,8004                                        # CERT # 4
7234           X2 X..28                          req=01,8004                                        # CERT # 5
7235           X2 X..28                          req=01,8004                                        # CERT # 6
7236           X2 X..28                          req=01,8004                                        # CERT # 7
7237           X2 X..28                          req=01,8004                                        # CERT # 8
7238           X2 X..28                          req=01,8004                                        # CERT # 9
7239           X2 X..28                          req=01,8004                                        # CERT # 10
7240           X..20                             req=01                                             # PROTOCOL
7241           N2,mediatype                      req=8017,8018                                      # AIDC MEDIA TYPE
7242           X..25                             req=8017,8018                                      # VCN
8001       *   N14                               req=01                                             # DIMENSIONS
8002           X..20                             req=01                                             # CMT No.
8003           N1 N13,csum,key X..16             dlpkey                                             # GRAI
8004           X..30,key                         dlpkey=7040                                        # GIAI
8005       *   N6                                req=01,02                                          # PRICE PER UNIT
8006       *   N14,csum,gcppos2 N2 N2            dlpkey=22,10,21                                    # ITIP
8007           X..34,iban                                                                           # IBAN
8008           N8,yymmddhh N..4,mmoptss          req=01,02                                          # PROD TIME
8009           X..50                             req=01                                             # OPTSEN
8010           Y..30,key                         dlpkey=8011                                        # CPID
8011           N..12,nozeroprefix                req=8010                                           # CPID SERIAL
8012           X..20                             req=01                                             # VERSION
8013           X..25,csumalpha,key               dlpkey                                             # GMN
8017       *   N18,csum,key                      ex=8018 dlpkey=8019                                # GSRN - PROVIDER
8018       *   N18,csum,key                      ex=8017 dlpkey=8019                                # GSRN - RECIPIENT
8019           N..10                             req=8017,8018                                      # SRIN
8020           X..25                             req=415                                            # REF No.
8026       *   N14,csum,gcppos2 N2 N2            dlpkey=22,10,21                                    # ITIP CONTENT
8030           X..90                                                                                # DIGSIG
8110           X..70,couponcode                                                                     # COUPON CODE
8111       *   N4                                req=255 ex=390n,391n,394n                          # POINTS
8112           X..70,couponposoffer                                                                 # COUPON OFFER
8200           X..70                             req=01                                             # PRODUCT URL
90             X..30                                                                                # INTERNAL
91             X..90                                                                                # INTERNAL
92             X..90                                                                                # INTERNAL
93             X..90                                                                                # INTERNAL
94             X..90                                                                                # INTERNAL
95             X..90                                                                                # INTERNAL
96             X..90                                                                                # INTERNAL
97             X..90                                                                                # INTERNAL
98             X..90                                                                                # INTERNAL
99             X..90                                                                                # INTERNAL
"""


def _parse_raw_dictionary() -> Dict[str, AIEntry]:
    """Parse the raw AI dictionary text into AIEntry objects."""
    entries = {}
    
    for line in RAW_AI_DICTIONARY.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # Skip header line
        if line.startswith('# AI'):
            continue
        
        # Parse line format: AI Flags Specification Attributes # Title
        # Handle the 'n' suffix for decimal position AIs (310n, 320n, etc.)
        parts = line.split('#')
        if len(parts) < 2:
            continue
            
        title = parts[1].strip()
        main_part = parts[0].strip()
        
        # Split main part into tokens
        tokens = main_part.split()
        if not tokens:
            continue
        
        ai_spec = tokens[0]
        
        # Check for fixed-length flag '*'
        fixed_length_flag = False
        spec_start = 1
        if len(tokens) > 1 and tokens[1] == '*':
            fixed_length_flag = True
            spec_start = 2
        elif len(tokens) > 1 and tokens[1] == '*?':
            fixed_length_flag = True
            spec_start = 2
        elif len(tokens) > 1 and tokens[1] == '?':
            spec_start = 2
        
        # Get specification
        spec = tokens[spec_start] if spec_start < len(tokens) else ''
        
        # Parse attributes (req=, ex=, dlpkey, etc.)
        attributes = ' '.join(tokens[spec_start + 1:]) if spec_start + 1 < len(tokens) else ''
        
        required_ais = []
        exclusive_ais = []
        is_dlp_key = False
        
        for attr in attributes.split():
            if attr.startswith('req='):
                required_ais = attr[4:].split(',')
            elif attr.startswith('ex='):
                exclusive_ais = attr[3:].split(',')
            elif attr.startswith('dlpkey'):
                is_dlp_key = True
        
        # Handle AI ranges with 'n' suffix (310n -> 3100-3109)
        if ai_spec.endswith('n'):
            base_ai = ai_spec[:-1]
            for n in range(10):
                ai_code = f"{base_ai}{n}"
                entry = _create_ai_entry(
                    ai_code, title, spec, fixed_length_flag,
                    required_ais, exclusive_ais, is_dlp_key,
                    decimal_position=n
                )
                entries[ai_code] = entry
        # Handle ranges like 3110-3115
        elif '-' in ai_spec and ai_spec[0].isdigit():
            start, end = ai_spec.split('-')
            for i in range(int(start), int(end) + 1):
                ai_code = str(i)
                decimal_pos = i % 10 if len(ai_code) == 4 else None
                entry = _create_ai_entry(
                    ai_code, title, spec, fixed_length_flag,
                    required_ais, exclusive_ais, is_dlp_key,
                    decimal_position=decimal_pos
                )
                entries[ai_code] = entry
        else:
            entry = _create_ai_entry(
                ai_spec, title, spec, fixed_length_flag,
                required_ais, exclusive_ais, is_dlp_key
            )
            entries[ai_spec] = entry
    
    return entries


def _create_ai_entry(
    ai: str,
    title: str,
    spec: str,
    fixed_length_flag: bool,
    required_ais: List[str],
    exclusive_ais: List[str],
    is_dlp_key: bool,
    decimal_position: Optional[int] = None
) -> AIEntry:
    """Create an AIEntry from parsed specification."""
    
    # Parse specification components
    components = []
    total_min_len = 0
    total_max_len = 0
    data_type = 'X'
    date_format = None
    has_check_digit = False
    
    # Handle multiple components separated by space
    spec_parts = spec.split()
    
    for part in spec_parts:
        dtype, min_len, max_len, linters = _parse_syntax_spec(part)
        components.append({
            'type': dtype,
            'min': min_len,
            'max': max_len,
            'linters': linters
        })
        total_min_len += min_len
        total_max_len += max_len
        data_type = dtype
        
        # Check for date format
        for linter in linters:
            if linter in ('yymmdd', 'yymmd0', 'yyyymmdd'):
                date_format = linter.upper()
            elif linter == 'yymmddhh':
                date_format = 'YYMMDDHH'
            elif linter in ('csum', 'csumalpha'):
                has_check_digit = True
    
    # Determine if fixed length (no separator required)
    fixed_length = None
    separator_required = True
    
    if fixed_length_flag:
        fixed_length = total_max_len
        separator_required = False
    
    entry = AIEntry(
        ai=ai,
        title=title,
        fixed_length=fixed_length,
        max_length=total_max_len,
        min_length=total_min_len,
        data_type=data_type,
        separator_required=separator_required,
        check_digit=has_check_digit,
        decimal_positions=decimal_position,
        date_format=date_format,
        required_ais=required_ais,
        exclusive_ais=exclusive_ais,
        components=components,
        is_dlp_key=is_dlp_key
    )
    
    # Build validation regex
    entry.regex = _build_regex_for_ai(entry)
    
    return entry


class AIDictionary:
    """
    Manages the complete GS1 AI Dictionary with trie-based lookup.
    """
    
    def __init__(self, entries: Optional[Dict[str, AIEntry]] = None):
        self.trie = AITrie()
        self._entries: Dict[str, AIEntry] = {}
        
        if entries:
            for ai, entry in entries.items():
                self.add(ai, entry)
    
    def add(self, ai: str, entry: AIEntry) -> None:
        """Add an AI entry to the dictionary."""
        self.trie.insert(ai, entry)
        self._entries[ai] = entry
    
    def get(self, ai: str) -> Optional[AIEntry]:
        """Get AI entry by code."""
        return self.trie.get(ai)
    
    def find_longest_match(self, text: str, start: int = 0) -> Tuple[Optional[AIEntry], int]:
        """Find longest matching AI at position."""
        return self.trie.find_longest_match(text, start)
    
    def __contains__(self, ai: str) -> bool:
        return ai in self._entries
    
    def __len__(self) -> int:
        return len(self._entries)
    
    def all_entries(self) -> Dict[str, AIEntry]:
        """Return all AI entries."""
        return self._entries.copy()
    
    def to_json(self) -> str:
        """Export dictionary to JSON."""
        data = {}
        for ai, entry in self._entries.items():
            data[ai] = {
                'ai': entry.ai,
                'title': entry.title,
                'fixed_length': entry.fixed_length,
                'max_length': entry.max_length,
                'min_length': entry.min_length,
                'data_type': entry.data_type,
                'separator_required': entry.separator_required,
                'regex': entry.regex,
                'check_digit': entry.check_digit,
                'decimal_positions': entry.decimal_positions,
                'date_format': entry.date_format,
                'required_ais': entry.required_ais,
                'exclusive_ais': entry.exclusive_ais,
                'is_dlp_key': entry.is_dlp_key,
            }
        return json.dumps(data, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'AIDictionary':
        """Load dictionary from JSON."""
        data = json.loads(json_str)
        entries = {}
        for ai, info in data.items():
            entries[ai] = AIEntry(
                ai=info['ai'],
                title=info['title'],
                fixed_length=info.get('fixed_length'),
                max_length=info.get('max_length', 0),
                min_length=info.get('min_length', 0),
                data_type=info.get('data_type', 'X'),
                separator_required=info.get('separator_required', True),
                regex=info.get('regex'),
                check_digit=info.get('check_digit', False),
                decimal_positions=info.get('decimal_positions'),
                date_format=info.get('date_format'),
                required_ais=info.get('required_ais', []),
                exclusive_ais=info.get('exclusive_ais', []),
                is_dlp_key=info.get('is_dlp_key', False),
            )
        return cls(entries)


# Global cached dictionary instance
_cached_dictionary: Optional[AIDictionary] = None


def load_ai_dictionary(
    json_path: Optional[Path] = None,
    force_reload: bool = False
) -> AIDictionary:
    """
    Load the AI dictionary, using cache when possible.
    
    Args:
        json_path: Optional path to a prebuilt JSON dictionary file.
        force_reload: Force reload even if cached.
    
    Returns:
        AIDictionary instance ready for use.
    """
    global _cached_dictionary
    
    if _cached_dictionary is not None and not force_reload and json_path is None:
        return _cached_dictionary
    
    if json_path and json_path.exists():
        with open(json_path, 'r', encoding='utf-8') as f:
            _cached_dictionary = AIDictionary.from_json(f.read())
    else:
        # Parse from embedded dictionary
        entries = _parse_raw_dictionary()
        _cached_dictionary = AIDictionary(entries)
    
    return _cached_dictionary


def save_ai_dictionary(dictionary: AIDictionary, json_path: Path) -> None:
    """Save AI dictionary to JSON file for faster loading."""
    with open(json_path, 'w', encoding='utf-8') as f:
        f.write(dictionary.to_json())
