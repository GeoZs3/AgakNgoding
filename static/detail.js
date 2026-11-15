function openQrModal() {
    const el = document.getElementById('qrModalBackdrop');
    if (el) el.classList.add('open');
}

function closeQrModal() {
    const el = document.getElementById('qrModalBackdrop');
    if (el) el.classList.remove('open');
}

function openEditModal() {
    const el = document.getElementById('editModalBackdrop');
    if (el) el.classList.add('open');
}

function closeEditModal() {
    const el = document.getElementById('editModalBackdrop');
    if (el) el.classList.remove('open');
}

function closeModalOnBackdrop(event, backdropId) {
    if (event.target.id === backdropId) {
        document.getElementById(backdropId).classList.remove('open');
    }
}

/* --- SEARCHABLE COMBOBOX JENIS TANAMAN & LOKASI PADA MODAL EDIT --- */
const EDIT_CFG_EL = document.getElementById('detailEditConfig');
if (EDIT_CFG_EL) {
    const EDIT_DATA = JSON.parse(EDIT_CFG_EL.textContent).metadata || {
        sectors: [],
        subsectors: [],
        plant_types: []
    };
    let editSectorId = null;

    const initialSectorName = (document.getElementById('editSectorInput')?.value || '').trim().toLowerCase();
    const matchedInitial = EDIT_DATA.sectors.find(s => s.name.toLowerCase() === initialSectorName);
    if (matchedInitial) {
        editSectorId = matchedInitial.id;
    }

    function makeAutoCode(text, maxLen = 4) {
        const words = text.toUpperCase().replace(/[^A-Z0-9\s]/g, '').trim().split(/\s+/).filter(Boolean);
        if (!words.length) return 'NEW';
        if (words.length === 1) return words[0].slice(0, maxLen);
        const initials = words.map(w => w[0]).join('').slice(0, maxLen);
        return initials.length >= 2 ? initials : words[0].slice(0, maxLen);
    }

    function attachEditCombo({ inputEl, dropdownEl, getItems, onSelect, onNewEntry }) {
        if (!inputEl || !dropdownEl) return;

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
                html += `<div class="combo-option" data-idx="${idx}"><span>${it.label}</span>${codeBadge}</div>`;
            });

            const exactMatch = items.some(it => it.label.toLowerCase() === qLower);
            if (query && !exactMatch) {
                html += `<div class="combo-option combo-create-new" data-create="1">+ Buat baru: <strong>"${query}"</strong></div>`;
            }

            dropdownEl.innerHTML = html || `<div class="combo-empty">Ketik untuk mencari...</div>`;
            dropdownEl.classList.add('open');

            dropdownEl.querySelectorAll('.combo-option[data-idx]').forEach(el => {
                el.addEventListener('mousedown', (e) => {
                    e.preventDefault();
                    const chosen = filtered[parseInt(el.dataset.idx, 10)];
                    inputEl.value = chosen.label;
                    dropdownEl.classList.remove('open');
                    onSelect(chosen);
                });
            });

            const createEl = dropdownEl.querySelector('.combo-create-new');
            if (createEl) {
                createEl.addEventListener('mousedown', (e) => {
                    e.preventDefault();
                    dropdownEl.classList.remove('open');
                    onNewEntry(query);
                });
            }
        }

        inputEl.addEventListener('focus', renderOptions);
        inputEl.addEventListener('input', () => {
            renderOptions();
            onNewEntry(inputEl.value.trim());
        });
        inputEl.addEventListener('blur', () => {
            setTimeout(() => dropdownEl.classList.remove('open'), 150);
        });
    }

    attachEditCombo({
        inputEl: document.getElementById('editPlantTypeInput'),
        dropdownEl: document.getElementById('editDropdownPlantType'),
        getItems: () => (EDIT_DATA.plant_types || []).map(t => ({ id: t.id, label: t.name, code: t.code })),
        onSelect: (chosen) => {
            document.getElementById('editPlantTypeCodeInput').value = chosen.code;
        },
        onNewEntry: (val) => {
            const exact = (EDIT_DATA.plant_types || []).find(t => t.name.toLowerCase() === val.toLowerCase());
            document.getElementById('editPlantTypeCodeInput').value = exact ? exact.code : makeAutoCode(val, 4);
        }
    });

    attachEditCombo({
        inputEl: document.getElementById('editSectorInput'),
        dropdownEl: document.getElementById('editDropdownSector'),
        getItems: () => EDIT_DATA.sectors.map(s => ({ id: s.id, label: s.name, code: s.code })),
        onSelect: (chosen) => {
            editSectorId = chosen.id;
            document.getElementById('editSectorCodeInput').value = chosen.code;
        },
        onNewEntry: (val) => {
            const exact = EDIT_DATA.sectors.find(s => s.name.toLowerCase() === val.toLowerCase());
            editSectorId = exact ? exact.id : null;
            document.getElementById('editSectorCodeInput').value = exact ? exact.code : makeAutoCode(val, 4);
        }
    });

    attachEditCombo({
        inputEl: document.getElementById('editSubsectorInput'),
        dropdownEl: document.getElementById('editDropdownSubsector'),
        getItems: () => {
            const list = editSectorId
                ? EDIT_DATA.subsectors.filter(sub => sub.sector_id === editSectorId)
                : EDIT_DATA.subsectors;
            return list.map(sub => ({ id: sub.id, label: sub.name, code: sub.code }));
        },
        onSelect: (chosen) => {
            document.getElementById('editSubsectorCodeInput').value = chosen.code;
        },
        onNewEntry: (val) => {
            const exact = EDIT_DATA.subsectors.find(
                sub => sub.name.toLowerCase() === val.toLowerCase() &&
                       (!editSectorId || sub.sector_id === editSectorId)
            );
            document.getElementById('editSubsectorCodeInput').value = exact ? exact.code : makeAutoCode(val, 5);
        }
    });
}