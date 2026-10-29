/**
 * Telua Docs - Interactive Diagram Utilities
 * Features:
 *   - Auto-attach Zoom and SVG Download buttons to ALL Mermaid diagrams (Class, Sequence, etc.)
 *   - Fullscreen Zoom Modal with interactive controls (+, -, Reset, Wheel zoom, Pan/Drag)
 *   - High-DPI Vector SVG export
 *   - Clean UI without button overlaps and with prominent Close button
 */
(function() {
    var currentScale = 1.0;
    var currentSvgElement = null;
    var isPanning = false;
    var didDrag = false;
    var startX = 0, startY = 0;
    var scrollLeft = 0, scrollTop = 0;

    function createModalOnce() {
        if (document.getElementById('mermaid-modal')) return;

        var modal = document.createElement('div');
        modal.id = 'mermaid-modal';
        modal.className = 'mermaid-modal';
        modal.innerHTML = 
            '<div class="mermaid-modal-content">' +
            '  <div class="mermaid-modal-header">' +
            '    <span class="mermaid-modal-title">🔍 Architecture Diagram (Fullscreen Viewer)</span>' +
            '    <div class="mermaid-modal-controls">' +
            '      <button class="mermaid-ctrl-btn" id="mermaid-btn-zoom-out" title="Zoom Out (−)">−</button>' +
            '      <span class="mermaid-scale-display" id="mermaid-scale-val">100%</span>' +
            '      <button class="mermaid-ctrl-btn" id="mermaid-btn-zoom-in" title="Zoom In (+)">+</button>' +
            '      <button class="mermaid-ctrl-btn" id="mermaid-btn-reset" title="Fit to Screen">Fit / Reset</button>' +
            '      <button class="mermaid-ctrl-btn mermaid-download-btn" id="mermaid-btn-download" title="Download Vector SVG">📥 SVG</button>' +
            '      <button class="mermaid-ctrl-btn mermaid-close-btn" id="mermaid-btn-close" title="Close Window (Esc)">✕ Close</button>' +
            '    </div>' +
            '  </div>' +
            '  <div id="mermaid-modal-viewport" title="Click outside or press Esc to close">' +
            '    <div id="mermaid-modal-body"></div>' +
            '  </div>' +
            '</div>';
        document.body.appendChild(modal);

        var viewport = document.getElementById('mermaid-modal-viewport');
        var closeBtn = document.getElementById('mermaid-btn-close');
        var zoomInBtn = document.getElementById('mermaid-btn-zoom-in');
        var zoomOutBtn = document.getElementById('mermaid-btn-zoom-out');
        var resetBtn = document.getElementById('mermaid-btn-reset');
        var dlBtn = document.getElementById('mermaid-btn-download');

        function closeModal() {
            modal.classList.remove('active');
            currentSvgElement = null;
        }

        // Close on Esc key
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && modal.classList.contains('active')) {
                closeModal();
            }
        });

        // Close button click
        closeBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            closeModal();
        });

        // Close when clicking directly on modal background or empty viewport area
        modal.addEventListener('click', function(e) {
            if (e.target === modal) closeModal();
        });

        viewport.addEventListener('click', function(e) {
            if (e.target === viewport && !didDrag) {
                closeModal();
            }
        });

        // Zoom In / Out / Reset
        zoomInBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            updateScale(currentScale + 0.25);
        });
        zoomOutBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            updateScale(Math.max(0.25, currentScale - 0.25));
        });
        resetBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            fitDiagramToViewport();
        });

        // Download SVG from inside modal
        dlBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            if (!currentSvgElement) return;
            downloadSvg(currentSvgElement, 'diagram_exported');
        });

        // Mouse Wheel Zoom
        viewport.addEventListener('wheel', function(e) {
            e.preventDefault();
            var delta = e.deltaY > 0 ? -0.15 : 0.15;
            updateScale(Math.max(0.25, Math.min(5.0, currentScale + delta)));
        }, { passive: false });

        // Pan / Drag viewport
        viewport.addEventListener('mousedown', function(e) {
            if (e.button !== 0) return; // Only left click
            isPanning = true;
            didDrag = false;
            startX = e.pageX - viewport.offsetLeft;
            startY = e.pageY - viewport.offsetTop;
            scrollLeft = viewport.scrollLeft;
            scrollTop = viewport.scrollTop;
        });

        window.addEventListener('mouseup', function() {
            isPanning = false;
        });

        viewport.addEventListener('mousemove', function(e) {
            if (!isPanning) return;
            e.preventDefault();
            var x = e.pageX - viewport.offsetLeft;
            var y = e.pageY - viewport.offsetTop;
            var walkX = (x - startX) * 1.5;
            var walkY = (y - startY) * 1.5;
            if (Math.abs(walkX) > 4 || Math.abs(walkY) > 4) {
                didDrag = true;
            }
            viewport.scrollLeft = scrollLeft - walkX;
            viewport.scrollTop = scrollTop - walkY;
        });
    }

    function updateScale(newScale) {
        currentScale = Math.round(newScale * 100) / 100;
        var body = document.getElementById('mermaid-modal-body');
        var scaleDisplay = document.getElementById('mermaid-scale-val');
        if (body) {
            body.style.transform = 'scale(' + currentScale + ')';
        }
        if (scaleDisplay) {
            scaleDisplay.textContent = Math.round(currentScale * 100) + '%';
        }
    }

    function fitDiagramToViewport() {
        var viewport = document.getElementById('mermaid-modal-viewport');
        var svg = document.querySelector('#mermaid-modal-body svg');
        if (!viewport || !svg) {
            updateScale(1.0);
            return;
        }

        var vW = viewport.clientWidth - 80;
        var vH = viewport.clientHeight - 80;
        if (vW <= 0 || vH <= 0) {
            updateScale(1.0);
            return;
        }

        var svgW = parseFloat(svg.getAttribute('width')) || svg.clientWidth || 800;
        var svgH = parseFloat(svg.getAttribute('height')) || svg.clientHeight || 600;

        var scaleW = vW / svgW;
        var scaleH = vH / svgH;
        var optimalScale = Math.min(scaleW, scaleH);

        // Optimal scale clamped between 0.6x and 2.5x
        optimalScale = Math.max(0.6, Math.min(2.5, optimalScale));
        updateScale(optimalScale);

        // Center scroll
        setTimeout(function() {
            viewport.scrollLeft = (viewport.scrollWidth - viewport.clientWidth) / 2;
            viewport.scrollTop = (viewport.scrollHeight - viewport.clientHeight) / 2;
        }, 30);
    }

    function openModalWithSvg(sourceSvg) {
        createModalOnce();
        var modal = document.getElementById('mermaid-modal');
        var modalBody = document.getElementById('mermaid-modal-body');
        if (!modal || !modalBody) return;

        currentSvgElement = sourceSvg;

        // Use outerHTML for reliable cross-browser SVG cloning
        modalBody.innerHTML = sourceSvg.outerHTML;
        var clone = modalBody.querySelector('svg');
        if (!clone) return;

        // Extract intrinsic dimensions from viewBox
        var vb = clone.getAttribute('viewBox') || sourceSvg.getAttribute('viewBox');
        var baseW = 800;
        var baseH = 600;
        if (vb) {
            var parts = vb.trim().split(/[\s,]+/);
            if (parts.length === 4) {
                baseW = parseFloat(parts[2]) || 800;
                baseH = parseFloat(parts[3]) || 600;
            }
        } else {
            baseW = sourceSvg.clientWidth || 800;
            baseH = sourceSvg.clientHeight || 600;
        }

        // Set explicit dimensions to guarantee SVG never collapses to 0x0
        clone.setAttribute('width', baseW);
        clone.setAttribute('height', baseH);
        clone.style.width = baseW + 'px';
        clone.style.height = baseH + 'px';
        clone.style.maxWidth = 'none';
        clone.style.maxHeight = 'none';
        clone.style.display = 'block';

        // Show modal
        modal.classList.add('active');

        // Set scale immediately so it renders visible right away
        updateScale(1.0);

        // Fit & enlarge after browser finishes layout calculation
        setTimeout(fitDiagramToViewport, 50);
    }

    function downloadSvg(svg, filename) {
        var svgData = new XMLSerializer().serializeToString(svg);
        if (!svgData.match(/^<\?xml/)) {
            svgData = '<?xml version="1.0" encoding="utf-8"?>\n' + svgData;
        }
        var svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
        var svgUrl = URL.createObjectURL(svgBlob);
        var link = document.createElement('a');
        link.href = svgUrl;
        link.download = (filename || 'diagram') + '.svg';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(svgUrl);
    }

    function initMermaidToolbars() {
        createModalOnce();

        // Select diagram containers in the page (EXCLUDING inside the modal)
        var containers = document.querySelectorAll('.mermaid, div[class*="mermaid"]');
        if (!containers.length) return;

        containers.forEach(function(container, idx) {
            // NEVER attach toolbar inside modal!
            if (container.closest('#mermaid-modal')) return;

            // Avoid duplicate toolbar
            if (container.querySelector('.mermaid-toolbar')) return;

            var svg = container.querySelector('svg');
            if (!svg) return;

            container.style.position = 'relative';

            var toolbar = document.createElement('div');
            toolbar.className = 'mermaid-toolbar';

            // Zoom button
            var zoomBtn = document.createElement('button');
            zoomBtn.className = 'mermaid-btn mermaid-btn-zoom';
            zoomBtn.type = 'button';
            zoomBtn.innerHTML = '🔍 Zoom';
            zoomBtn.title = 'Enlarge diagram fullscreen';
            zoomBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                openModalWithSvg(svg);
            });

            // Download SVG button
            var dlBtn = document.createElement('button');
            dlBtn.className = 'mermaid-btn mermaid-btn-download';
            dlBtn.type = 'button';
            dlBtn.innerHTML = '📥 SVG';
            dlBtn.title = 'Download high-res vector SVG';
            dlBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                downloadSvg(svg, 'diagram_' + (idx + 1));
            });

            toolbar.appendChild(zoomBtn);
            toolbar.appendChild(dlBtn);
            container.appendChild(toolbar);
        });
    }

    // Initialize on load and on DOM updates
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            setTimeout(initMermaidToolbars, 300);
            setTimeout(initMermaidToolbars, 1000);
        });
    } else {
        setTimeout(initMermaidToolbars, 300);
        setTimeout(initMermaidToolbars, 1000);
    }

    var observer = new MutationObserver(function() {
        initMermaidToolbars();
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
})();
