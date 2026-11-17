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

// 1. Combobox Nama Tanaman
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

// =========================================================================
// 5. DIALOG SUMBER FOTO: DARI FILE ATAU DARI KAMERA (getUserMedia + Canvas)
// =========================================================================
(function initPhotoCaptureModal() {
    const photoInput = document.getElementById('photoInput');
    const modal = document.getElementById('photoSourceModal');
    const openBtn = document.getElementById('openPhotoDialogBtn');
    const changeBtn = document.getElementById('changePhotoBtn');
    const closeBtn = document.getElementById('closePhotoDialogBtn');
    const fromFileBtn = document.getElementById('chooseFromFileBtn');
    const fromCamBtn = document.getElementById('chooseFromCameraBtn');
    const cameraBox = document.getElementById('cameraStreamBox');
    const videoEl = document.getElementById('cameraVideoPreview');
    const canvasEl = document.getElementById('cameraCaptureCanvas');
    const captureBtn = document.getElementById('captureFrameBtn');
    const cancelCamBtn = document.getElementById('cancelCameraBtn');
    const errorBox = document.getElementById('cameraErrorMsg');

    const emptyPrompt = document.getElementById('photoEmptyPrompt');
    const previewWrapper = document.getElementById('photoPreviewWrapper');
    const previewImg = document.getElementById('photoPreviewImg');
    const formEl = document.getElementById('addPlantForm');

    let activeMediaStream = null;
    const MAX_FILE_BYTES = 5 * 1024 * 1024;
    const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

    function stopCameraStream() {
        if (activeMediaStream) {
            activeMediaStream.getTracks().forEach(track => track.stop());
            activeMediaStream = null;
        }
        if (videoEl) {
            videoEl.srcObject = null;
        }
        if (cameraBox) {
            cameraBox.classList.remove('active');
        }
    }

    function showCameraError(message) {
        if (!errorBox) return;
        errorBox.textContent = message;
        errorBox.style.display = 'block';
    }

    function clearCameraError() {
        if (!errorBox) return;
        errorBox.textContent = '';
        errorBox.style.display = 'none';
    }

    function openModal() {
        clearCameraError();
        stopCameraStream();
        if (modal) modal.classList.add('open');
    }

    function closeModal() {
        stopCameraStream();
        clearCameraError();
        if (modal) modal.classList.remove('open');
    }

    function applySelectedFileToPreview(file) {
        if (!file) return false;
        if (!ALLOWED_TYPES.includes(file.type)) {
            showCameraError('Format file tidak didukung. Gunakan PNG, JPG, atau WEBP.');
            return false;
        }
        if (file.size > MAX_FILE_BYTES) {
            showCameraError('Ukuran file foto melebihi batas 5 MB.');
            return false;
        }

        const reader = new FileReader();
        reader.onload = (ev) => {
            previewImg.src = ev.target.result;
            emptyPrompt.style.display = 'none';
            previewWrapper.classList.add('active');
            closeModal();
        };
        reader.readAsDataURL(file);
        return true;
    }

    if (openBtn) openBtn.addEventListener('click', openModal);
    if (changeBtn) changeBtn.addEventListener('click', openModal);
    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });
    }

    // Pilihan 1: Dari File
    if (fromFileBtn && photoInput) {
        fromFileBtn.addEventListener('click', () => {
            clearCameraError();
            stopCameraStream();
            photoInput.click();
        });

        photoInput.addEventListener('change', () => {
            if (photoInput.files && photoInput.files[0]) {
                const ok = applySelectedFileToPreview(photoInput.files[0]);
                if (!ok) {
                    photoInput.value = '';
                }
            }
        });
    }

    // Pilihan 2: Dari Kamera
    if (fromCamBtn) {
        fromCamBtn.addEventListener('click', async () => {
            clearCameraError();
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                showCameraError('Browser atau konteks koneksi ini tidak mendukung API kamera. Gunakan HTTPS/localhost atau pilih "Dari File".');
                return;
            }

            try {
                activeMediaStream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: { ideal: 'environment' } },
                    audio: false
                });
                videoEl.srcObject = activeMediaStream;
                cameraBox.classList.add('active');
            } catch (err) {
                if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
                    showCameraError('Izin akses kamera ditolak oleh pengguna. Izinkan kamera di pengaturan browser atau pilih "Dari File".');
                } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
                    showCameraError('Perangkat kamera tidak ditemukan. Silakan pilih foto "Dari File".');
                } else {
                    showCameraError(`Kamera tidak dapat diakses (${err.message || err.name}).`);
                }
            }
        });
    }

    // Tangkap frame video ke Canvas -> File input
    if (captureBtn) {
        captureBtn.addEventListener('click', () => {
            if (!videoEl || !videoEl.videoWidth || !videoEl.videoHeight) {
                showCameraError('Kamera belum siap mengambil gambar.');
                return;
            }

            canvasEl.width = videoEl.videoWidth;
            canvasEl.height = videoEl.videoHeight;
            const ctx = canvasEl.getContext('2d');
            ctx.drawImage(videoEl, 0, 0, canvasEl.width, canvasEl.height);

            canvasEl.toBlob((blob) => {
                if (!blob) {
                    showCameraError('Gagal memproses hasil tangkapan kamera.');
                    return;
                }
                const capturedFile = new File([blob], `camera_${Date.now()}.jpg`, {
                    type: 'image/jpeg'
                });
                const dt = new DataTransfer();
                dt.items.add(capturedFile);
                photoInput.files = dt.files;

                applySelectedFileToPreview(capturedFile);
            }, 'image/jpeg', 0.9);
        });
    }

    if (cancelCamBtn) {
        cancelCamBtn.addEventListener('click', () => {
            stopCameraStream();
            clearCameraError();
        });
    }

    // Pastikan foto wajib ada sebelum submit form
    if (formEl) {
        formEl.addEventListener('submit', (e) => {
            if (!photoInput.files || photoInput.files.length === 0) {
                e.preventDefault();
                openModal();
                showCameraError('Foto utama tanaman wajib dipilih atau diambil dari kamera sebelum menyimpan.');
            }
        });
    }
})();