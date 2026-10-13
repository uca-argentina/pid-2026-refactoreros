(() => {
  const form = document.querySelector('[data-validation-form]');
  if (!form) return;
  const video = document.querySelector('[data-camera]');
  const start = document.querySelector('[data-start-camera]');
  const cameraButtonLabel = document.querySelector('[data-camera-button-label]');
  const cameraCloseMark = document.querySelector('[data-camera-close-mark]');
  const cameraPicker = document.querySelector('[data-camera-picker]');
  const cameraDevice = document.querySelector('[data-camera-device]');
  const status = document.querySelector('[data-scanner-status]');
  const reservationCode = document.querySelector('[data-reservation-code]');
  const previewButton = form.querySelector('[data-preview]');
  const codeCharacters = reservationCode ? [...reservationCode.querySelectorAll('[data-code-character]')] : [];
  const codeInput = form.elements.code;
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d', { willReadFrequently: true });
  const MAX_SCAN_DIMENSION = 960;
  const SCAN_INTERVAL_MS = 80;
  let stream = null;
  let frame = null;
  let generation = 0;
  let previewSubmitting = false;
  let lastScanAt = 0;

  context.imageSmoothingEnabled = false;

  function showPreviewLoading() {
    if (previewSubmitting) return;

    previewSubmitting = true;
    if (start) start.disabled = true;
    if (!previewButton) return;

    previewButton.disabled = true;
    previewButton.classList.add('is-loading');
    previewButton.setAttribute('aria-busy', 'true');
    previewButton.textContent = 'Buscando entrada…';
  }

  function setStatus(message) {
    status.textContent = message;
    status.classList.toggle('is-visible', Boolean(message));
  }

  function validCharacters(value) {
    return value.toUpperCase().replace(/[^A-Z2-9]/g, '');
  }

  function syncReservationCode() {
    codeInput.value = codeCharacters.map(input => input.value).join('');
  }

  function fillReservationCode(value, startAt = 0) {
    const characters = validCharacters(value);
    let index = startAt;
    for (const character of characters) {
      if (index >= codeCharacters.length) break;
      codeCharacters[index].value = character;
      index += 1;
    }
    syncReservationCode();
    return Math.min(index, codeCharacters.length - 1);
  }

  if (codeCharacters.length) {
    const initialValue = validCharacters(codeInput.value);
    codeCharacters.forEach((input, index) => { input.value = initialValue[index] || ''; });
    syncReservationCode();

    codeCharacters.forEach((input, index) => {
      input.addEventListener('input', () => {
        const nextIndex = fillReservationCode(input.value, index);
        if (input.value && index < codeCharacters.length - 1) codeCharacters[nextIndex].focus();
      });
      input.addEventListener('keydown', event => {
        if (event.key !== 'Backspace') return;
        event.preventDefault();
        if (input.value) {
          input.value = '';
          syncReservationCode();
          return;
        }
        if (index > 0) {
          codeCharacters[index - 1].value = '';
          codeCharacters[index - 1].focus();
          syncReservationCode();
        }
      });
      input.addEventListener('paste', event => {
        event.preventDefault();
        const nextIndex = fillReservationCode(event.clipboardData.getData('text'), index);
        codeCharacters[nextIndex].focus();
      });
    });
  }

  const admissionForm = document.querySelector('[data-confirm-admission]');
  if (admissionForm) {
    const admissionButton = admissionForm.querySelector('[data-validate-admission]');
    const availableSeats = admissionForm.dataset.availableSeats;
    const isSingleAdmission = admissionForm.dataset.singleAdmission === 'true';
    let admissionSubmitting = false;
    const updateAdmissionButton = () => {
      if (isSingleAdmission) {
        admissionButton.disabled = false;
        admissionButton.textContent = 'Validar ingreso (única butaca)';
        return;
      }
      const selected = admissionForm.querySelectorAll('input[name="ticket_numbers"]:checked').length;
      admissionButton.disabled = selected === 0;
      admissionButton.textContent = selected
        ? `Validar ingreso (${selected} / ${availableSeats} butacas)`
        : 'Validar ingreso';
    };
    admissionForm.querySelectorAll('input[name="ticket_numbers"]').forEach(input => {
      input.addEventListener('change', updateAdmissionButton);
    });
    const selectAllSeats = admissionForm.querySelector('[data-select-all-seats]');
    if (selectAllSeats) {
      selectAllSeats.addEventListener('click', () => {
        admissionForm.querySelectorAll('input[name="ticket_numbers"]').forEach(input => {
          input.checked = true;
        });
        updateAdmissionButton();
      });
    }
    admissionForm.addEventListener('submit', event => {
      if (admissionSubmitting) {
        event.preventDefault();
        return;
      }
      admissionSubmitting = true;
      admissionButton.disabled = true;
      admissionButton.textContent = 'Validando ingreso…';
    });
    updateAdmissionButton();
  }

  const undoButtons = [...document.querySelectorAll('[data-undo-validation]')];
  if (undoButtons.length) {
    const updateUndoButtons = () => {
      const now = Date.now() / 1000;
      undoButtons.forEach(button => {
        if (button.dataset.undoExpired === 'true' || button.dataset.undoSubmitting === 'true') return;
        const remaining = Math.max(0, Number(button.dataset.undoDeadline) - now);
        const undoWindowSeconds = Number(button.dataset.undoWindowSeconds) || 30;
        const countdown = button.querySelector('[data-undo-countdown]');
        if (remaining <= 0) {
          const status = document.createElement('span');
          status.className = 'validation-history-status';
          status.textContent = 'Validada';
          button.closest('form').replaceWith(status);
          button.dataset.undoExpired = 'true';
          return;
        }
        button.style.setProperty('--undo-progress', `${(remaining / undoWindowSeconds) * 100}%`);
        countdown.textContent = ` · 0:${String(Math.ceil(remaining)).padStart(2, '0')}`;
      });
    };
    undoButtons.forEach(button => {
      const undoForm = button.closest('form');
      if (!undoForm) return;
      undoForm.addEventListener('submit', event => {
        if (button.dataset.undoSubmitting === 'true') {
          event.preventDefault();
          return;
        }
        button.dataset.undoSubmitting = 'true';
        button.disabled = true;
        button.querySelector('span').textContent = 'Deshaciendo…';
        const countdown = button.querySelector('[data-undo-countdown]');
        if (countdown) countdown.textContent = '';
      });
    });
    updateUndoButtons();
    window.setInterval(updateUndoButtons, 250);
  }

  const foundEntry = document.querySelector('[data-found-entry]');
  if (foundEntry) {
    window.requestAnimationFrame(() => {
      foundEntry.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  function stopCamera() {
    generation += 1;
    if (frame) cancelAnimationFrame(frame);
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = null;
    video.srcObject = null;
    video.hidden = true;
    start.disabled = false;
    start.classList.remove('is-camera-open');
    if (cameraButtonLabel) cameraButtonLabel.textContent = 'Escanear código';
    if (cameraCloseMark) cameraCloseMark.hidden = true;
    if (cameraPicker) {
      cameraPicker.hidden = true;
      cameraPicker.open = false;
    }
  }

  async function populateCameraPicker(selectedDeviceId) {
    if (!cameraPicker || !cameraDevice || !navigator.mediaDevices?.enumerateDevices) return;
    const cameras = (await navigator.mediaDevices.enumerateDevices())
      .filter(device => device.kind === 'videoinput');
    cameraDevice.replaceChildren();
    cameras.forEach((camera, index) => {
      const option = document.createElement('option');
      option.value = camera.deviceId;
      option.textContent = camera.label || `Cámara ${index + 1}`;
      option.selected = camera.deviceId === selectedDeviceId;
      cameraDevice.append(option);
    });
    cameraPicker.hidden = cameras.length < 2;
  }

  async function defaultCameraId() {
    if (!navigator.mediaDevices?.enumerateDevices) return '';
    try {
      const cameras = (await navigator.mediaDevices.enumerateDevices())
        .filter(device => device.kind === 'videoinput');
      // The browser exposes cameras in the same order shown by the picker.
      // Start with index 0; an operator can still choose another one explicitly.
      return cameras[0]?.deviceId || '';
    } catch (_error) {
      return '';
    }
  }

  function decode(source, width, height) {
    const scale = Math.min(1, MAX_SCAN_DIMENSION / Math.max(width, height));
    const scanWidth = Math.round(width * scale);
    const scanHeight = Math.round(height * scale);
    if (canvas.width !== scanWidth || canvas.height !== scanHeight) {
      canvas.width = scanWidth;
      canvas.height = scanHeight;
    }
    context.drawImage(source, 0, 0, canvas.width, canvas.height);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
    return window.jsQR(pixels.data, pixels.width, pixels.height, {
      // Tickets use a dark QR over a light background. Avoiding the inverted
      // pass halves the decoder work for every captured frame.
      inversionAttempts: 'dontInvert',
    });
  }

  function accept(result) {
    if (!result || !/^BC2:[A-Za-z2-9]{6}$/i.test(result.data)) return false;
    stopCamera();
    form.elements.code.value = result.data.slice(4).toUpperCase();
    setStatus('QR leído. Consultando entrada…');
    form.requestSubmit(form.querySelector('[data-preview]'));
    return true;
  }

  function scan(now) {
    if (!stream) return;
    if (
      video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA
      && now - lastScanAt >= SCAN_INTERVAL_MS
    ) {
      lastScanAt = now;
      if (accept(decode(video, video.videoWidth, video.videoHeight))) return;
    }
    frame = requestAnimationFrame(scan);
  }

  async function startCamera(deviceId = null) {
    if (!window.isSecureContext) {
      setStatus('La cámara solo funciona por HTTPS. Abrí el panel con una URL segura y permití la cámara en Brave.');
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.jsQR) {
      setStatus('No se pudo habilitar el lector. Podés ingresar el código manualmente.');
      return;
    }
    start.disabled = true;
    const current = ++generation;
    try {
      if (frame) cancelAnimationFrame(frame);
      frame = null;
      if (stream) stream.getTracks().forEach(track => track.stop());
      stream = null;
      const requestedDeviceId = deviceId === null ? await defaultCameraId() : deviceId;
      const videoConstraints = {
        ...(requestedDeviceId
          ? { deviceId: { exact: requestedDeviceId } }
          : { facingMode: { ideal: 'environment' } }),
        // Avoid opening a 4K stream only to downscale it into the scan canvas.
        width: { ideal: 1280, max: 1920 },
        height: { ideal: 720, max: 1080 },
      };
      const acquired = await navigator.mediaDevices.getUserMedia({ video: videoConstraints, audio: false });
      if (current !== generation) {
        acquired.getTracks().forEach(track => track.stop());
        return;
      }
      stream = acquired;
      video.srcObject = stream;
      video.hidden = false;
      await video.play();
      const activeDeviceId = stream.getVideoTracks()[0]?.getSettings().deviceId || requestedDeviceId;
      await populateCameraPicker(activeDeviceId);
      start.disabled = false;
      start.classList.add('is-camera-open');
      if (cameraButtonLabel) cameraButtonLabel.textContent = 'Cerrar cámara';
      if (cameraCloseMark) cameraCloseMark.hidden = false;
      setStatus('Apuntá al QR de una entrada.');
      lastScanAt = 0;
      frame = requestAnimationFrame(scan);
    } catch (error) {
      stopCamera();
      setStatus('No pudimos abrir la cámara. Revisá los permisos o ingresá el código manualmente.');
    }
  }

  start.addEventListener('click', () => {
    if (previewSubmitting) return;
    if (stream) {
      stopCamera();
      setStatus('Cámara cerrada.');
      return;
    }
    startCamera();
  });
  if (cameraDevice) {
    cameraDevice.addEventListener('change', () => {
      if (cameraDevice.value) startCamera(cameraDevice.value);
    });
  }
  form.addEventListener('submit', event => {
    if (previewSubmitting) {
      event.preventDefault();
      return;
    }
    stopCamera();
    showPreviewLoading();
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden) stopCamera(); });
  window.addEventListener('pagehide', stopCamera);
})();
