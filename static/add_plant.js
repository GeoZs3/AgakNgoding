const CONFIG_EL = document.getElementById('addPlantConfig');
const APP_CONFIG = CONFIG_EL ? JSON.parse(CONFIG_EL.textContent) : {};
const METADATA = APP_CONFIG.metadata || {
    sectors: [],
    subsectors: [],
    plant_types: [],
    plant_managers: [],
    sector_managers: [],
    known_plants: []
};
const LOGGED_MANAGER_CODE = APP_CONFIG.loggedManagerCode || '';

let selectedSectorId = null;
let selectedSubsectorNextSeq = 1;

function makeAutoCode(text, maxLen = 4) {
    const words = text.toUpperCase().replace(/[^A-Z0-9\s]/g, '').trim().split(/\s+/).filter(Boolean);
    if (!words.length) return 'NEW';
    if (words.length === 1) return words[0].slice(0, maxLen);
    const initials = words.map(w => w[0]).join('').slice(0, maxLen);
    return initials.length >= 2 ? initials : words[0].slice(0, maxLen);
}

function attachSearchableCombo({ inputEl, dropdownEl, getItems, onSelect, onNewEntry }) {
    function renderOptions() {
        const query = inputEl.value.trim();
        const qLower = query.toLowerCase();
        const items = getItems();

        const filtered = items.filter(it =>
            it.label.toLowerCase().includes(qLower) ||
            (it.code && it.code.toLowerCase().includes(qLower))
        );

        let html = '';
        filtered.forEach((it, idx) => {
            const codeBadge = it.code ? `<span class="combo-code-badge">${it.code}</span>` : '';
            html += `
                <div class="combo-option" data-idx="${idx}">
                    <span>${it.label}</span>
                    ${codeBadge}
                </div>
            `;
        });

        const exactMatch = items.some(it => it.label.toLowerCase() === qLower);
        if (query && !exactMatch) {
            html += `
                <div class="combo-option combo-create-new" data-create="1">
                    + Buat entri baru: <strong>"${query}"</strong>
                </div>
            `;
        }

        if (!html) {
            html = `<div class="combo-empty">Ketik untuk mencari atau membuat entri baru...</div>`;
        }

        dropdownEl.innerHTML = html;
        dropdownEl.classList.add('open');

        dropdownEl.querySelectorAll('.combo-option[data-idx]').forEach(el => {
            el.addEventListener('mousedown', (e) => {
                e.preventDefault();
                const chosen = filtered[parseInt(el.dataset.idx, 10)];
                inputEl.value = chosen.label;
                dropdownEl.classList.remove('open');
                onSelect(chosen);
                updatePublicIdPreview();
            });
        });

        const createEl = dropdownEl.querySelector('.combo-create-new');
        if (createEl) {
            createEl.addEventListener('mousedown', (e) => {
                e.preventDefault();
                dropdownEl.classList.remove('open');
                onNewEntry(query);
                updatePublicIdPreview();
            });
        }
    }

    inputEl.addEventListener('focus', renderOptions);
    inputEl.addEventListener('input', () => {
        renderOptions();
        onNewEntry(inputEl.value.trim());
        updatePublicIdPreview();
    });
    inputEl.addEventListener('blur', () => {
        setTimeout(() => dropdownEl.classList.remove('open'), 150);
    });
}

// 1. Combobox Nama Tanaman (otomatis mengisi jenis tanaman jika sudah ada di arsip)
attachSearchableCombo({
    inputEl: document.getElementById('plantNameInput'),
    dropdownEl: document.getElementById('dropdownPlantName'),
    getItems: () => METADATA.known_plants.map(p => ({ label: p.name, raw: p })),
    onSelect: (chosen) => {
        const p = chosen.raw;
        if (p.plant_type_id) {
            const pt = METADATA.plant_types.find(t => t.id === p.plant_type_id);
            if (pt) {
                document.getElementById('plantTypeInput').value = pt.name;
                document.getElementById('plantTypeCodeInput').value = pt.code;
            }
        }
    },
    onNewEntry: () => {}
});

// 2. Combobox Jenis Tanaman
attachSearchableCombo({
    inputEl: document.getElementById('plantTypeInput'),
    dropdownEl: document.getElementById('dropdownPlantType'),
    getItems: () => METADATA.plant_types.map(t => ({ id: t.id, label: t.name, code: t.code })),
    onSelect: (chosen) => {
        document.getElementById('plantTypeCodeInput').value = chosen.code;
    },
    onNewEntry: (val) => {
        const exact = METADATA.plant_types.find(t => t.name.toLowerCase() === val.toLowerCase());
        document.getElementById('plantTypeCodeInput').value = exact ? exact.code : makeAutoCode(val, 4);
    }
});

// 3. Combobox Sektor Sekolah
attachSearchableCombo({
    inputEl: document.getElementById('sectorInput'),
    dropdownEl: document.getElementById('dropdownSector'),
    getItems: () => METADATA.sectors.map(s => ({ id: s.id, label: s.name, code: s.code })),
    onSelect: (chosen) => {
        selectedSectorId = chosen.id;
        document.getElementById('sectorCodeInput').value = chosen.code;
        if (!LOGGED_MANAGER_CODE) {
            const sm = METADATA.sector_managers.find(x => x.sector_id === chosen.id);
            if (sm) {
                document.getElementById('managerSelect').value = sm.manager_code;
            }
        }
    },
    onNewEntry: (val) => {
        const exact = METADATA.sectors.find(s => s.name.toLowerCase() === val.toLowerCase());
        selectedSectorId = exact ? exact.id : null;
        document.getElementById('sectorCodeInput').value = exact ? exact.code : makeAutoCode(val, 4);
    }
});

// 4. Combobox Subsektor Spesifik
attachSearchableCombo({
    inputEl: document.getElementById('subsectorInput'),
    dropdownEl: document.getElementById('dropdownSubsector'),
    getItems: () => {
        const list = selectedSectorId
            ? METADATA.subsectors.filter(sub => sub.sector_id === selectedSectorId)
            : METADATA.subsectors;
        return list.map(sub => ({
            id: sub.id,
            label: sub.name,
            code: sub.code,
            next_seq: sub.next_seq
        }));
    },
    onSelect: (chosen) => {
        document.getElementById('subsectorCodeInput').value = chosen.code;
        selectedSubsectorNextSeq = chosen.next_seq || 1;
    },
    onNewEntry: (val) => {
        const exact = METADATA.subsectors.find(
            sub => sub.name.toLowerCase() === val.toLowerCase() &&
                   (!selectedSectorId || sub.sector_id === selectedSectorId)
        );
        document.getElementById('subsectorCodeInput').value = exact ? exact.code : makeAutoCode(val, 5);
        selectedSubsectorNextSeq = exact ? (exact.next_seq || 1) : 1;
    }
});

function updatePublicIdPreview() {
    const secCode = document.getElementById('sectorCodeInput').value.trim() || 'SEKTOR';
    const subCode = document.getElementById('subsectorCodeInput').value.trim() || 'SUB';
    const seqFormatted = String(selectedSubsectorNextSeq).padStart(3, '0');
    const typeCode = document.getElementById('plantTypeCodeInput').value.trim() || 'TIPE';
    const mgrSel = document.getElementById('managerSelect');
    const mgrCode = mgrSel && mgrSel.value ? mgrSel.value : 'P';

    document.getElementById('publicIdPreview').textContent =
        `${secCode}-${subCode}-${seqFormatted}-${typeCode}-${mgrCode}`;
}

updatePublicIdPreview();