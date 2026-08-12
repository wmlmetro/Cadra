odoo.define('myservice_barcode_station.BarcodeStation', ['web.AbstractAction', 'web.core', 'web.rpc'], function(require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var rpc = require('web.rpc');

    var DOMAIN_COLORS = {
        plant:    '#E85426',
        building: '#007bff',
        plumbing: '#17a2b8',
        security: '#dc3545',
        fleet:    '#6f42c1',
        it:       '#20c997',
        furniture:'#888',
        other:    '#aaa',
    };

    var DOMAIN_LABELS = {
        plant:    'Plant & Machinery',
        building: 'Building Services',
        plumbing: 'Plumbing & Drainage',
        security: 'Security & Safety',
        fleet:    'Fleet',
        it:       'IT & Comms',
        furniture:'Furniture',
        other:    'Other',
    };

    var BarcodeStation = AbstractAction.extend({
        template: 'myservice_barcode_station.BarcodeStation',
        hasControlPanel: false,

        start: function() {
            var self = this;
            this._currentTagId = null;
            this._currentAssetId = null;
            this._allTags = [];
            this._cameraStream = null;
            this._barcodeDetector = null;

            return this._super.apply(this, arguments).then(function() {
                self._loadData();
                self._bindEvents();
            });
        },

        destroy: function() {
            this._stopCamera();
            this._super.apply(this, arguments);
        },

        refresh: function() {
            this._loadData();
        },

        _bindEvents: function() {
            var self = this;

            // Search input — Enter key
            this.$('#bc-search-input').on('keydown', function(e) {
                if (e.key === 'Enter') self._doLookup();
            });
            this.$('#bc-search-btn').on('click', function() { self._doLookup(); });

            // Mode tabs
            this.$('#btn-type').on('click', function() {
                self.$('#btn-type').addClass('active');
                self.$('#btn-camera').removeClass('active');
                self.$('#scan-type-mode').show();
                self.$('#scan-camera-mode').hide();
                self._stopCamera();
            });
            this.$('#btn-camera').on('click', function() {
                self.$('#btn-camera').addClass('active');
                self.$('#btn-type').removeClass('active');
                self.$('#scan-camera-mode').show();
                self.$('#scan-type-mode').hide();
            });

            // Camera
            this.$('#bc-camera-start').on('click', function() { self._startCamera(); });
            this.$('#bc-camera-stop').on('click', function() { self._stopCamera(); });

            // Result actions
            this.$('#res-print-btn').on('click', function() { self._printTag(); });
            this.$('#res-view-btn').on('click', function() { self._viewAsset(); });
            this.$('#res-replace-btn').on('click', function() { self._requestReplacement(); });

            // Batch print
            this.$('#batch-print-execute').on('click', function() { self._batchPrint(); });
            this.$('#bc-batch-print-btn').on('click', function() { self._batchPrint(); });

            // Domain filter
            this.$('#bc-domain-filter').on('change', function() {
                self._renderTagList();
                self._renderDomainBreakdown();
            });
        },

        _loadData: function() {
            var self = this;
            // Load KPIs
            rpc.query({ route: '/barcode/kpis', params: {} }).then(function(kpis) {
                var set = function(id, val) {
                    var el = document.getElementById(id);
                    if (el) el.textContent = val;
                };
                set('kpi-total-assets', kpis.total_assets || 0);
                set('kpi-active-tags',  kpis.active_tags  || 0);
                set('kpi-pending',      kpis.pending_replacement || 0);
                set('kpi-scrapped',     kpis.scrapped_tags || 0);
                set('kpi-untagged',     kpis.untagged || 0);
            });
            // Load tags
            rpc.query({ route: '/barcode/recent_tags', params: { limit: 200 } }).then(function(tags) {
                self._allTags = tags || [];
                self._renderTagList();
                self._renderDomainBreakdown();
                var el = document.getElementById('bc-last-updated');
                if (el) {
                    var now = new Date();
                    el.textContent = 'Last updated: ' + now.toLocaleTimeString('en-GB', {hour:'2-digit',minute:'2-digit'});
                }
            });
        },

        _doLookup: function() {
            var self = this;
            var query = this.$('#bc-search-input').val().trim();
            if (!query) return;
            this.$('#bc-result-panel').hide();
            this.$('#bc-not-found').hide();

            rpc.query({ route: '/barcode/lookup', params: { query: query } }).then(function(res) {
                if (!res.found) {
                    self.$('#bc-not-found').show();
                } else {
                    self._showResult(res);
                }
            });
        },

        _showResult: function(res) {
            this._currentTagId = res.tag_id;
            this._currentAssetId = res.asset_id;
            var set = function(id, val) {
                var el = document.getElementById(id);
                if (el) el.textContent = val || '—';
            };
            set('res-tag-number',  res.tag_number);
            set('res-asset-name',  res.asset_name);
            set('res-category',    res.category);
            set('res-domain',      res.domain);
            set('res-location',    res.location);
            set('res-custodian',   res.custodian);
            set('res-condition',   res.condition);
            set('res-last-pm',     res.last_service_date || 'Not recorded');
            set('res-next-pm',     res.next_service_date || 'Not scheduled');
            set('res-sap',         res.sap_asset_number || 'N/A');

            var pill = document.getElementById('res-state');
            if (pill) {
                pill.textContent = res.tag_state === 'active' ? 'Active' :
                                   res.tag_state === 'pending' ? 'Replacement Pending' : 'Scrapped';
                pill.style.background = res.tag_state === 'active' ? '#e8f5e9' :
                                        res.tag_state === 'pending' ? '#fff3cd' : '#f4f4f4';
                pill.style.color = res.tag_state === 'active' ? '#28a745' :
                                   res.tag_state === 'pending' ? '#856404' : '#888';
            }
            this.$('#bc-result-panel').show();
        },

        _printTag: function() {
            if (!this._currentTagId) return;
            var size = this.$('input[name="label-size"]:checked').val() || 'medium';
            rpc.query({
                route: '/barcode/print_url',
                params: { tag_id: this._currentTagId, size: size }
            }).then(function(res) {
                if (res.url) window.open(res.url, '_blank');
            });
        },

        _viewAsset: function() {
            if (!this._currentAssetId) return;
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'nrs.asset',
                res_id: this._currentAssetId,
                views: [[false, 'form']],
                target: 'current',
            });
        },

        _requestReplacement: function() {
            var self = this;
            if (!this._currentTagId) return;
            rpc.query({
                model: 'nrs.asset.tag.label',
                method: 'action_request_replacement',
                args: [[this._currentTagId]],
            }).then(function() {
                self.do_notify('Replacement requested', 'A tag replacement request has been submitted for manager approval.');
                self._loadData();
            });
        },

        _batchPrint: function() {
            var domain = this.$('#batch-domain-select').val();
            var size   = this.$('#batch-size-select').val() || 'medium';
            // Get tag IDs for domain
            var tags = this._allTags.filter(function(t) {
                return !domain || t.domain === domain;
            });
            if (!tags.length) {
                alert('No tags found for selection.');
                return;
            }
            // The label reports are registered on nrs.asset, so the report URL
            // takes ASSET ids — passing tag ids renders unrelated assets.
            var ids = tags.map(function(t) { return t.asset_id; })
                          .filter(function(id) { return !!id; })
                          .join(',');
            if (!ids) {
                alert('No assets found for selection.');
                return;
            }
            var reportMap = {
                small:  'myservice_asset_register/action_report_asset_tag_small',
                medium: 'myservice_asset_register/action_report_asset_tag',
                large:  'myservice_asset_register/action_report_asset_tag_large',
                sheet:  'myservice_asset_register/action_report_asset_tag_sheet',
            };
            var reportName = reportMap[size] || reportMap.medium;
            window.open('/report/pdf/' + reportName + '/' + ids, '_blank');
        },

        _renderTagList: function() {
            var self = this;
            var domainFilter = this.$('#bc-domain-filter').val();
            var tags = this._allTags.filter(function(t) {
                return !domainFilter || t.domain === domainFilter;
            });

            var $list = this.$('#bc-tag-list');
            $list.empty();

            var countEl = document.getElementById('bc-tag-count');
            if (countEl) countEl.textContent = tags.length + ' tags';

            if (!tags.length) {
                $list.html('<div style="padding:20px;text-align:center;font-size:12px;color:#aaa">No tags found.</div>');
                return;
            }

            tags.slice(0, 100).forEach(function(t) {
                var color = DOMAIN_COLORS[t.domain] || '#aaa';
                var badgeClass = t.tag_state === 'active' ? 'bc-b-active' :
                                 t.tag_state === 'pending' ? 'bc-b-pending' : 'bc-b-scrapped';
                var badge = t.tag_state === 'active' ? 'Active' :
                            t.tag_state === 'pending' ? 'Replacement pending' : 'Scrapped';
                $list.append(
                    '<div class="ms-bc-tag-row" data-tag-id="' + t.tag_id + '" data-asset-id="' + t.asset_id + '">' +
                    '<div class="ms-bc-tag-dot" style="background:' + color + '"></div>' +
                    '<div style="flex:1;min-width:0">' +
                    '<div class="ms-bc-tag-num">' + t.tag_number + '</div>' +
                    '<div class="ms-bc-tag-asset">' + t.asset_name + '</div>' +
                    '<div class="ms-bc-tag-loc">' + (t.location || '') + '</div>' +
                    '</div>' +
                    '<span class="ms-bc-tag-badge ' + badgeClass + '">' + badge + '</span>' +
                    '</div>'
                );
            });

            // Click on tag row to lookup
            this.$('.ms-bc-tag-row').on('click', function() {
                var tagId = parseInt($(this).data('tag-id'));
                var tag = self._allTags.find(function(t) { return t.tag_id === tagId; });
                if (tag) {
                    self.$('#bc-search-input').val(tag.tag_number);
                    self._doLookup();
                }
            });
        },

        _renderDomainBreakdown: function() {
            var $el = this.$('#bc-domain-breakdown');
            $el.empty();

            var counts = {};
            this._allTags.forEach(function(t) {
                counts[t.domain] = (counts[t.domain] || 0) + 1;
            });
            var sorted = Object.entries(counts).sort(function(a,b) { return b[1]-a[1]; });
            var max = sorted.length ? sorted[0][1] : 1;

            sorted.forEach(function(entry) {
                var domain = entry[0], count = entry[1];
                var color = DOMAIN_COLORS[domain] || '#aaa';
                var label = DOMAIN_LABELS[domain] || domain;
                var pct = Math.round(count / max * 100);
                $el.append(
                    '<div class="ms-bc-dom-row">' +
                    '<div class="ms-bc-dom-name">' + label + '</div>' +
                    '<div class="ms-bc-dom-bar-track">' +
                    '<div class="ms-bc-dom-bar-fill" style="width:' + pct + '%;background:' + color + '"></div>' +
                    '</div>' +
                    '<div class="ms-bc-dom-count">' + count + '</div>' +
                    '</div>'
                );
            });
        },

        // ── Camera scanning ──────────────────────────────────
        _startCamera: function() {
            var self = this;
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                this.$('#camera-status').text('Camera not supported on this device/browser.');
                return;
            }
            navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
                .then(function(stream) {
                    self._cameraStream = stream;
                    var video = document.getElementById('bc-video');
                    video.srcObject = stream;
                    video.style.display = 'block';
                    self.$('#camera-placeholder').hide();
                    self.$('#bc-camera-start').hide();
                    self.$('#bc-camera-stop').show();
                    self.$('#camera-status').text('Camera active — point at barcode');
                    self._startBarcodeDetection(video);
                })
                .catch(function(err) {
                    self.$('#camera-status').text('Camera error: ' + err.message);
                });
        },

        _startBarcodeDetection: function(video) {
            var self = this;
            // Use BarcodeDetector API if available
            if (typeof BarcodeDetector !== 'undefined') {
                this._barcodeDetector = new BarcodeDetector({ formats: ['code_128', 'qr_code', 'ean_13'] });
                var detect = function() {
                    if (!self._cameraStream) return;
                    self._barcodeDetector.detect(video).then(function(barcodes) {
                        if (barcodes.length > 0) {
                            var code = barcodes[0].rawValue;
                            self.$('#bc-search-input').val(code);
                            self.$('#camera-status').text('Detected: ' + code);
                            self._stopCamera();
                            self._doLookup();
                        } else {
                            requestAnimationFrame(detect);
                        }
                    }).catch(function() {
                        requestAnimationFrame(detect);
                    });
                };
                requestAnimationFrame(detect);
            } else {
                this.$('#camera-status').text('Camera active. BarcodeDetector not available — type code manually.');
            }
        },

        _stopCamera: function() {
            if (this._cameraStream) {
                this._cameraStream.getTracks().forEach(function(t) { t.stop(); });
                this._cameraStream = null;
            }
            var video = document.getElementById('bc-video');
            if (video) { video.style.display = 'none'; video.srcObject = null; }
            this.$('#camera-placeholder') && this.$('#camera-placeholder').show();
            this.$('#bc-camera-start') && this.$('#bc-camera-start').show();
            this.$('#bc-camera-stop') && this.$('#bc-camera-stop').hide();
        },
    });

    core.action_registry.add('barcode_station', BarcodeStation);
    return BarcodeStation;
});
