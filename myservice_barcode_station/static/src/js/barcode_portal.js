/* NRS Barcode Portal — field team scanner */
(function() {
    var cameraStream = null;
    var barcodeDetector = null;
    var scanning = false;

    function lookup(query) {
        if (!query) return;
        document.getElementById('portal-result').style.display = 'none';
        document.getElementById('portal-not-found').style.display = 'none';

        fetch('/tags/lookup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: { query: query } })
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var res = data.result;
            if (!res || !res.found) {
                document.getElementById('portal-not-found').style.display = 'block';
                return;
            }
            var set = function(id, val) {
                var el = document.getElementById(id);
                if (el) el.textContent = val || '—';
            };
            set('p-tag-number', res.tag_number);
            set('p-asset-name', res.asset_name);
            set('p-category',   res.category);
            set('p-location',   res.location);
            set('p-custodian',  '—');
            set('p-last-pm',    res.last_service_date || 'Not recorded');

            var condEl = document.getElementById('p-condition');
            if (condEl) {
                condEl.textContent = res.condition || '—';
                condEl.className = 'ms-portal-result-val ms-portal-condition-' + (res.condition || 'good');
            }
            var stateEl = document.getElementById('p-state');
            if (stateEl) {
                stateEl.textContent = res.state === 'active' ? 'Active' :
                                      res.state === 'in_repair' ? 'Under Repair' :
                                      res.state === 'missing' ? 'MISSING' : res.state || '—';
                stateEl.style.color = res.state === 'active' ? '#28a745' :
                                      res.state === 'missing' ? '#dc3545' : '#f0a500';
            }
            document.getElementById('portal-result').style.display = 'block';
            document.getElementById('portal-result').scrollIntoView({ behavior: 'smooth' });
        })
        .catch(function(e) {
            document.getElementById('portal-not-found').style.display = 'block';
        });
    }

    function startCamera() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            setStatus('Camera not supported. Please type the tag number.');
            return;
        }
        navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
            .then(function(stream) {
                cameraStream = stream;
                var video = document.getElementById('portal-video');
                video.srcObject = stream;
                video.style.display = 'block';
                document.getElementById('portal-cam-start').style.display = 'none';
                document.getElementById('portal-cam-stop').style.display = 'block';
                document.getElementById('portal-scan-line').style.display = 'block';
                setStatus('Point camera at barcode...');
                startDetection(video);
            })
            .catch(function(e) {
                setStatus('Camera error: ' + e.message);
            });
    }

    function startDetection(video) {
        scanning = true;
        if (typeof BarcodeDetector !== 'undefined') {
            barcodeDetector = new BarcodeDetector({ formats: ['code_128', 'qr_code', 'code_39'] });
            var detect = function() {
                if (!scanning || !cameraStream) return;
                barcodeDetector.detect(video).then(function(codes) {
                    if (codes.length > 0) {
                        var code = codes[0].rawValue;
                        setStatus('Detected: ' + code);
                        stopCamera();
                        document.getElementById('portal-search-input').value = code;
                        lookup(code);
                    } else {
                        requestAnimationFrame(detect);
                    }
                }).catch(function() {
                    requestAnimationFrame(detect);
                });
            };
            requestAnimationFrame(detect);
        } else {
            setStatus('Camera active. BarcodeDetector API not available on this browser — enter code manually.');
        }
    }

    function stopCamera() {
        scanning = false;
        if (cameraStream) {
            cameraStream.getTracks().forEach(function(t) { t.stop(); });
            cameraStream = null;
        }
        var video = document.getElementById('portal-video');
        if (video) { video.style.display = 'none'; video.srcObject = null; }
        var sl = document.getElementById('portal-scan-line');
        if (sl) sl.style.display = 'none';
        var start = document.getElementById('portal-cam-start');
        if (start) start.style.display = 'block';
        var stop = document.getElementById('portal-cam-stop');
        if (stop) stop.style.display = 'none';
        setStatus('');
    }

    function setStatus(msg) {
        var el = document.getElementById('portal-status');
        if (el) el.textContent = msg;
    }

    // Init on DOM ready
    document.addEventListener('DOMContentLoaded', function() {
        var searchInput = document.getElementById('portal-search-input');
        var searchBtn   = document.getElementById('portal-search-btn');
        var camStart    = document.getElementById('portal-cam-start');
        var camStop     = document.getElementById('portal-cam-stop');

        if (searchInput) {
            searchInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') lookup(searchInput.value.trim());
            });
            // Auto-focus for USB scanner keyboards
            searchInput.focus();
        }
        if (searchBtn) searchBtn.addEventListener('click', function() {
            lookup(searchInput ? searchInput.value.trim() : '');
        });
        if (camStart) camStart.addEventListener('click', startCamera);
        if (camStop)  camStop.addEventListener('click', stopCamera);
    });
})();
