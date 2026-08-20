import os
import struct
import re

def compile_po(po_filepath, mo_filepath):
    """
    Properly compiles a UTF-8 encoded .po file to a GNU gettext binary .mo file.
    """
    with open(po_filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse entries
    entries = {}
    # Pattern to match msgid and msgstr blocks
    pattern = re.compile(r'msgid\s+("(?:[^"\\]|\\.)*")(?:\s*"(?:[^"\\]|\\.)*")*\s+msgstr\s+("(?:[^"\\]|\\.)*")(?:\s*"(?:[^"\\]|\\.)*")*', re.MULTILINE)
    
    # Simpler line-by-line parser
    lines = content.splitlines()
    cur_id = []
    cur_str = []
    mode = None # 'id' or 'str'

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('msgid '):
            if cur_id and cur_str:
                entries["".join(cur_id)] = "".join(cur_str)
                cur_id = []
                cur_str = []
            val = line[6:].strip()
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1].replace('\\"', '"').replace('\\n', '\n')
            cur_id.append(val)
            mode = 'id'
        elif line.startswith('msgstr '):
            val = line[7:].strip()
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1].replace('\\"', '"').replace('\\n', '\n')
            cur_str.append(val)
            mode = 'str'
        elif line.startswith('"') and line.endswith('"'):
            val = line[1:-1].replace('\\"', '"').replace('\\n', '\n')
            if mode == 'id':
                cur_id.append(val)
            elif mode == 'str':
                cur_str.append(val)

    if cur_id and cur_str:
        entries["".join(cur_id)] = "".join(cur_str)

    # Ensure header exists with explicit charset=UTF-8
    if "" not in entries:
        entries[""] = "MIME-Version: 1.0\nContent-Type: text/plain; charset=UTF-8\nContent-Transfer-Encoding: 8bit\n"
    elif "charset=" not in entries[""]:
        entries[""] += "Content-Type: text/plain; charset=UTF-8\n"

    # GNU gettext requires sorted original strings with "" at position 0
    sorted_keys = sorted(entries.keys())

    ids = b''
    strs = b''
    offsets = []

    for k in sorted_keys:
        v = entries[k]
        k_bytes = k.encode('utf-8')
        v_bytes = v.encode('utf-8')
        offsets.append((len(ids), len(k_bytes), len(strs), len(v_bytes)))
        ids += k_bytes + b'\x00'
        strs += v_bytes + b'\x00'

    n_strings = len(sorted_keys)
    keystart = 7 * 4 + 16 * n_strings
    valuestart = keystart + len(ids)

    koffsets = []
    voffsets = []
    for o1, l1, o2, l2 in offsets:
        koffsets.append((l1, o1 + keystart))
        voffsets.append((l2, o2 + valuestart))

    header = struct.pack('Iiiiiii',
        0x950412de,  # Magic number
        0,           # Format version
        n_strings,   # Number of strings
        7 * 4,       # Offset of original strings table
        7 * 4 + n_strings * 8, # Offset of translated strings table
        0,           # Size of hashing table
        0            # Offset of hashing table
    )

    output = bytearray(header)
    for l, o in koffsets:
        output += struct.pack('ii', l, o)
    for l, o in voffsets:
        output += struct.pack('ii', l, o)
    output += ids
    output += strs

    os.makedirs(os.path.dirname(mo_filepath), exist_ok=True)
    with open(mo_filepath, 'wb') as f:
        f.write(output)

    print(f"Compiled {n_strings} clean translations with UTF-8 header to {mo_filepath}")

if __name__ == '__main__':
    compile_po('locale/hi/LC_MESSAGES/django.po', 'locale/hi/LC_MESSAGES/django.mo')
