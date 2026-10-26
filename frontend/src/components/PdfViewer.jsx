import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

// Configure PDF.js worker using Vite asset URL
pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker

// -----------------------------------------------------------------------------
// Individual PDF Page Canvas Component
// -----------------------------------------------------------------------------
function PdfPageItem({ pdfDoc, pageNum, scale, rotation, onVisible }) {
  const canvasRef = useRef(null)
  const containerRef = useRef(null)
  const renderTaskRef = useRef(null)
  const [pageSize, setPageSize] = useState({ width: 0, height: 0 })
  const [rendering, setRendering] = useState(true)

  // Intersection Observer to detect active page during vertical scroll
  useEffect(() => {
    if (!containerRef.current || !onVisible) return
    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0]
        if (entry && entry.isIntersecting && entry.intersectionRatio >= 0.5) {
          onVisible(pageNum)
        }
      },
      { threshold: [0.5] }
    )
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [pageNum, onVisible])

  // Render page to canvas
  useEffect(() => {
    let isCancelled = false

    async function renderPage() {
      if (!pdfDoc || !canvasRef.current) return

      try {
        setRendering(true)
        const page = await pdfDoc.getPage(pageNum)
        if (isCancelled) return

        // Cancel previous ongoing render task if any
        if (renderTaskRef.current) {
          try {
            renderTaskRef.current.cancel()
          } catch (e) {
            // ignore cancellation
          }
        }

        const viewport = page.getViewport({ scale, rotation })
        setPageSize({ width: viewport.width, height: viewport.height })

        const canvas = canvasRef.current
        const dpr = window.devicePixelRatio || 1
        canvas.width = Math.floor(viewport.width * dpr)
        canvas.height = Math.floor(viewport.height * dpr)
        canvas.style.width = `${Math.floor(viewport.width)}px`
        canvas.style.height = `${Math.floor(viewport.height)}px`

        const ctx = canvas.getContext('2d')
        ctx.setTransform(1, 0, 0, 1, 0, 0)
        ctx.scale(dpr, dpr)

        const renderContext = {
          canvasContext: ctx,
          viewport: viewport,
        }

        const renderTask = page.render(renderContext)
        renderTaskRef.current = renderTask
        await renderTask.promise
        if (!isCancelled) {
          setRendering(false)
        }
      } catch (err) {
        if (err?.name !== 'RenderingCancelledException' && !isCancelled) {
          console.error(`Error rendering PDF page ${pageNum}:`, err)
          setRendering(false)
        }
      }
    }

    renderPage()

    return () => {
      isCancelled = true
      if (renderTaskRef.current) {
        try {
          renderTaskRef.current.cancel()
        } catch (e) {
          // ignore
        }
      }
    }
  }, [pdfDoc, pageNum, scale, rotation])

  return (
    <div
      ref={containerRef}
      id={`cpass-pdf-page-${pageNum}`}
      className="cpass-pdf-page-wrapper"
      data-page-num={pageNum}
      style={{
        width: pageSize.width ? `${pageSize.width}px` : '100%',
        minHeight: pageSize.height ? `${pageSize.height}px` : '200px',
      }}
    >
      <canvas ref={canvasRef} className="cpass-pdf-page-canvas" />
      {rendering && (
        <div className="cpass-pdf-page-loader">
          <span className="cpass-pdf-spinner" />
        </div>
      )}
      <div className="cpass-pdf-page-tag">Page {pageNum}</div>
    </div>
  )
}

// -----------------------------------------------------------------------------
// Thumbnail Item Component for Sidebar
// -----------------------------------------------------------------------------
function PdfThumbnailItem({ pdfDoc, pageNum, isActive, onClick }) {
  const canvasRef = useRef(null)
  const [rendered, setRendered] = useState(false)

  useEffect(() => {
    let isCancelled = false

    async function renderThumb() {
      if (!pdfDoc || !canvasRef.current || rendered) return
      try {
        const page = await pdfDoc.getPage(pageNum)
        if (isCancelled) return

        // Scale thumbnail to fit ~84px width
        const unscaledViewport = page.getViewport({ scale: 1.0 })
        const thumbScale = 84 / unscaledViewport.width
        const viewport = page.getViewport({ scale: thumbScale })

        const canvas = canvasRef.current
        canvas.width = Math.floor(viewport.width)
        canvas.height = Math.floor(viewport.height)

        const ctx = canvas.getContext('2d')
        const renderContext = {
          canvasContext: ctx,
          viewport: viewport,
        }

        await page.render(renderContext).promise
        if (!isCancelled) setRendered(true)
      } catch (e) {
        // ignore
      }
    }

    renderThumb()
    return () => { isCancelled = true }
  }, [pdfDoc, pageNum, rendered])

  return (
    <div
      className={`cpass-pdf-thumb-card ${isActive ? 'active' : ''}`}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onClick()}
      aria-label={`Go to page ${pageNum}`}
    >
      <div className="cpass-pdf-thumb-canvas-box">
        <canvas ref={canvasRef} className="cpass-pdf-thumb-canvas" />
      </div>
      <span className="cpass-pdf-thumb-num">Page {pageNum}</span>
    </div>
  )
}

// -----------------------------------------------------------------------------
// Dedicated Image Viewer Subcomponent (Shares layout, toolbar, and controls)
// -----------------------------------------------------------------------------
function ImageViewerContent({ fileUrl, fileName }) {
  const containerRef = useRef(null)
  const [scale, setScale] = useState(1.0)
  const [rotation, setRotation] = useState(0)
  const [isFitWidth, setIsFitWidth] = useState(true)

  // Zoom handlers for images
  const handleZoomIn = () => {
    setIsFitWidth(false)
    setScale((prev) => Math.min(3.0, Number((prev + 0.2).toFixed(2))))
  }

  const handleZoomOut = () => {
    setIsFitWidth(false)
    setScale((prev) => Math.max(0.3, Number((prev - 0.2).toFixed(2))))
  }

  const handleFitWidth = () => {
    setIsFitWidth(true)
    setScale(1.0)
  }

  const handleRotate = () => {
    setRotation((prev) => (prev + 90) % 360)
  }

  return (
    <div className="cpass-image-viewer-inner">
      {/* Secondary toolbar for image controls */}
      <div className="cpass-pdf-toolbar l1-no-print">
        <div className="cpass-pdf-toolbar-group">
          <span className="cpass-pdf-file-type-pill">🖼 Image</span>
        </div>

        <div className="cpass-pdf-toolbar-group cpass-pdf-nav-group">
          <span className="cpass-pdf-page-indicator">Single Image Document</span>
        </div>

        <div className="cpass-pdf-toolbar-group cpass-pdf-zoom-group">
          <button
            type="button"
            className="cpass-pdf-btn-tool"
            onClick={handleZoomOut}
            disabled={scale <= 0.3}
            title="Zoom Out (-)"
          >
            <span>−</span>
          </button>
          <span className="cpass-pdf-zoom-text">
            {isFitWidth ? 'Fit' : `${Math.round(scale * 100)}%`}
          </span>
          <button
            type="button"
            className="cpass-pdf-btn-tool"
            onClick={handleZoomIn}
            disabled={scale >= 3.0}
            title="Zoom In (+)"
          >
            <span>+</span>
          </button>
          <button
            type="button"
            className={`cpass-pdf-btn-tool ${isFitWidth ? 'active' : ''}`}
            onClick={handleFitWidth}
            title="Fit Width"
          >
            <span>⤢</span>
            <span className="cpass-pdf-btn-label">Fit Width</span>
          </button>
          <button
            type="button"
            className="cpass-pdf-btn-tool"
            onClick={handleRotate}
            title="Rotate 90 degrees"
          >
            <span>↺</span>
          </button>
        </div>
      </div>

      <div ref={containerRef} className="cpass-image-canvas-viewport">
        <div
          className="cpass-image-wrapper"
          style={{
            transform: `rotate(${rotation}deg)`,
            transition: 'transform 0.2s ease',
          }}
        >
          <img
            src={fileUrl}
            alt={fileName}
            className={`cpass-image-element ${isFitWidth ? 'fit-width' : ''}`}
            style={!isFitWidth ? { width: `${scale * 100}%` } : undefined}
          />
        </div>
      </div>
    </div>
  )
}

// -----------------------------------------------------------------------------
// Main Responsive Custom Document & PDF Viewer Component
// -----------------------------------------------------------------------------
export default function PdfViewer({
  fileUrl,
  fileName = 'Document',
  fileMeta,
  mimeType,
  isLoading = false,
  errorMessage = null,
  isReviewed = false,
  reviewedAt,
  onToggleReview,
  onDownload,
  onClose,
}) {
  // Detect if file is image vs PDF
  const isImage = useMemo(() => {
    if (mimeType?.startsWith('image/')) return true
    return /\.(jpe?g|png|webp|gif|bmp|svg)$/i.test(fileName || '')
  }, [mimeType, fileName])

  // PDF.js State
  const [pdfDoc, setPdfDoc] = useState(null)
  const [numPages, setNumPages] = useState(0)
  const [currentPage, setCurrentPage] = useState(1)
  const [scale, setScale] = useState(1.0)
  const [fitWidthScale, setFitWidthScale] = useState(1.0)
  const [isFitWidth, setIsFitWidth] = useState(true)
  const [rotation, setRotation] = useState(0)
  const [showThumbnails, setShowThumbnails] = useState(false) // Hidden by default
  const [loadingDoc, setLoadingDoc] = useState(true)
  const [docError, setDocError] = useState(null)

  const containerRef = useRef(null)
  const scrollAreaRef = useRef(null)

  // Calculate Fit Width Scale based on container's clientWidth
  const calculateFitWidth = useCallback(
    (doc = pdfDoc) => {
      if (!doc || !containerRef.current) return

      doc.getPage(1).then((page) => {
        const unscaledViewport = page.getViewport({ scale: 1.0, rotation })
        // Account for thumbnail sidebar (140px) if visible, plus container padding (24px)
        const sidebarWidth = showThumbnails ? 140 : 0
        const availableWidth = containerRef.current.clientWidth - sidebarWidth - 28
        if (availableWidth > 80) {
          const newFitScale = Math.max(0.3, Math.min(2.5, availableWidth / unscaledViewport.width))
          setFitWidthScale(newFitScale)
          if (isFitWidth) {
            setScale(newFitScale)
          }
        }
      }).catch((e) => console.error('Fit width calculation error:', e))
    },
    [pdfDoc, rotation, showThumbnails, isFitWidth]
  )

  // Load PDF Document when fileUrl changes (only if it's a PDF)
  useEffect(() => {
    let isCancelled = false
    if (!fileUrl || isImage) {
      setLoadingDoc(false)
      return
    }

    setLoadingDoc(true)
    setDocError(null)
    setPdfDoc(null)
    setCurrentPage(1)

    const loadingTask = pdfjsLib.getDocument({
      url: fileUrl,
      cMapPacked: true,
    })

    loadingTask.promise
      .then((doc) => {
        if (isCancelled) return
        setPdfDoc(doc)
        setNumPages(doc.numPages)
        setLoadingDoc(false)

        // Calculate initial fit width
        doc.getPage(1).then((firstPage) => {
          if (isCancelled || !containerRef.current) return
          const unscaled = firstPage.getViewport({ scale: 1.0, rotation: 0 })
          const available = containerRef.current.clientWidth - 28
          const initialScale = Math.max(0.3, Math.min(2.5, available / unscaled.width))
          setFitWidthScale(initialScale)
          setScale(initialScale)
          setIsFitWidth(true)
        })
      })
      .catch((err) => {
        if (isCancelled) return
        console.error('Failed to load PDF document:', err)
        setDocError(err.message || 'Unable to parse PDF document.')
        setLoadingDoc(false)
      })

    return () => {
      isCancelled = true
      try {
        loadingTask.destroy()
      } catch (e) {
        // ignore
      }
    }
  }, [fileUrl, isImage])

  // Observe container resize to auto-fit width responsively
  useEffect(() => {
    if (!containerRef.current || isImage) return
    const resizeObserver = new ResizeObserver(() => {
      if (isFitWidth) {
        calculateFitWidth()
      }
    })
    resizeObserver.observe(containerRef.current)
    return () => resizeObserver.disconnect()
  }, [calculateFitWidth, isFitWidth, isImage])

  // Page Scroll Jump Handler
  const scrollToPage = useCallback((targetPage) => {
    const pageNum = Math.max(1, Math.min(numPages, targetPage))
    setCurrentPage(pageNum)
    const targetEl = document.getElementById(`cpass-pdf-page-${pageNum}`)
    if (targetEl && scrollAreaRef.current) {
      targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [numPages])

  // Navigation handlers
  const handlePrevPage = () => {
    if (currentPage > 1) {
      scrollToPage(currentPage - 1)
    }
  }

  const handleNextPage = () => {
    if (currentPage < numPages) {
      scrollToPage(currentPage + 1)
    }
  }

  // Zoom handlers
  const handleZoomIn = () => {
    setIsFitWidth(false)
    setScale((prev) => Math.min(2.5, Number((prev + 0.15).toFixed(2))))
  }

  const handleZoomOut = () => {
    setIsFitWidth(false)
    setScale((prev) => Math.max(0.4, Number((prev - 0.15).toFixed(2))))
  }

  const handleFitWidthToggle = () => {
    setIsFitWidth(true)
    calculateFitWidth()
  }

  const handleRotate = () => {
    setRotation((prev) => (prev + 90) % 360)
  }

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return

      if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
        e.preventDefault()
        handlePrevPage()
      } else if (e.key === 'ArrowRight' || e.key === 'PageDown') {
        e.preventDefault()
        handleNextPage()
      } else if (e.key === '+' || e.key === '=') {
        e.preventDefault()
        handleZoomIn()
      } else if (e.key === '-' || e.key === '_') {
        e.preventDefault()
        handleZoomOut()
      } else if (e.key === '0') {
        e.preventDefault()
        handleFitWidthToggle()
      } else if (e.key === 'Escape' && onClose) {
        e.preventDefault()
        onClose()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [currentPage, numPages, onClose])

  // Array of page numbers
  const pagesList = useMemo(() => {
    return Array.from({ length: numPages }, (_, i) => i + 1)
  }, [numPages])

  const activeError = errorMessage || docError
  const activeLoading = isLoading || loadingDoc

  return (
    <div ref={containerRef} className="cpass-pdf-viewer-root">
      {/* ------------------------------------------------------------------
         Top Primary Header: Filename, Review Status, Download, Close
         ------------------------------------------------------------------ */}
      <div className="cpass-pdf-top-header l1-no-print">
        <div className="cpass-pdf-doc-info" title={fileName}>
          <span className="cpass-pdf-badge-icon">{isImage ? '🖼' : '📄'}</span>
          <div className="cpass-pdf-name-box">
            <span className="cpass-pdf-filename">{fileName}</span>
            {fileMeta && <span className="cpass-pdf-filemeta">{fileMeta}</span>}
          </div>
        </div>

        {/* Verification Checkbox */}
        {onToggleReview && (
          <div className="cpass-pdf-review-zone">
            <label className={`l2-review-checkbox-label ${isReviewed ? 'reviewed' : 'pending'}`}>
              <input
                type="checkbox"
                checked={Boolean(isReviewed)}
                onChange={(e) => onToggleReview(e.target.checked)}
              />
              <span>{isReviewed ? '✓ Verified by Manager' : 'Mark as Reviewed'}</span>
            </label>
            {isReviewed && reviewedAt && (
              <span className="cpass-pdf-reviewed-stamp">
                {new Date(reviewedAt).toLocaleDateString()}
              </span>
            )}
          </div>
        )}

        {/* Actions: Download and Close */}
        <div className="cpass-pdf-actions">
          {onDownload && (
            <button
              type="button"
              className="l2-btn-preview"
              onClick={onDownload}
              title="Download file to computer"
            >
              <span>⬇</span> Download
            </button>
          )}
          {onClose && (
            <button
              type="button"
              className="l1-btn-secondary"
              onClick={onClose}
              title="Close preview and return to list"
              style={{ padding: '6px 12px', fontSize: '12.5px' }}
            >
              ✕ Close
            </button>
          )}
        </div>
      </div>

      {/* ------------------------------------------------------------------
         Stream Loading State
         ------------------------------------------------------------------ */}
      {isLoading ? (
        <div className="cpass-pdf-status-screen">
          <span className="cpass-pdf-spinner large" />
          <h4>Retrieving Secure Document Stream…</h4>
          <p>Fetching encrypted document from Google Drive storage.</p>
        </div>
      ) : activeError ? (
        <div className="cpass-pdf-status-screen error">
          <span style={{ fontSize: '36px', marginBottom: '8px' }}>⚠️</span>
          <h4>Failed to Display Document</h4>
          <p>{activeError}</p>
          {onDownload && (
            <button
              type="button"
              className="l2-btn-preview"
              onClick={onDownload}
              style={{ marginTop: '12px' }}
            >
              ⬇ Download File Directly
            </button>
          )}
        </div>
      ) : isImage ? (
        /* Image Preview Rendering */
        <ImageViewerContent fileUrl={fileUrl} fileName={fileName} />
      ) : (
        /* PDF Document Rendering */
        <>
          {/* Secondary Toolbar: Thumbnails Toggle, Page Nav, Zoom, Fit Width */}
          <div className="cpass-pdf-toolbar l1-no-print">
            {/* Left: Thumbnail Sidebar Toggle */}
            <div className="cpass-pdf-toolbar-group">
              <button
                type="button"
                className={`cpass-pdf-btn-tool ${showThumbnails ? 'active' : ''}`}
                onClick={() => setShowThumbnails((prev) => !prev)}
                title={showThumbnails ? 'Hide thumbnail sidebar' : 'Show thumbnail sidebar'}
                disabled={activeLoading || numPages <= 1}
              >
                <span>📑</span>
                <span className="cpass-pdf-btn-label">Thumbnails</span>
              </button>
            </div>

            {/* Center: Page Navigation Controls */}
            <div className="cpass-pdf-toolbar-group cpass-pdf-nav-group">
              <button
                type="button"
                className="cpass-pdf-btn-tool"
                onClick={handlePrevPage}
                disabled={activeLoading || currentPage <= 1}
                title="Previous page (Left arrow)"
              >
                ◀
              </button>

              <span className="cpass-pdf-page-indicator">
                Page <strong>{numPages > 0 ? currentPage : '—'}</strong> of <strong>{numPages || '—'}</strong>
              </span>

              <button
                type="button"
                className="cpass-pdf-btn-tool"
                onClick={handleNextPage}
                disabled={activeLoading || currentPage >= numPages}
                title="Next page (Right arrow)"
              >
                ▶
              </button>
            </div>

            {/* Right: Zoom & View Controls */}
            <div className="cpass-pdf-toolbar-group cpass-pdf-zoom-group">
              <button
                type="button"
                className="cpass-pdf-btn-tool"
                onClick={handleZoomOut}
                disabled={activeLoading || scale <= 0.4}
                title="Zoom Out (-)"
              >
                <span>−</span>
              </button>

              <span className="cpass-pdf-zoom-text" title="Current zoom level">
                {isFitWidth ? 'Fit' : `${Math.round(scale * 100)}%`}
              </span>

              <button
                type="button"
                className="cpass-pdf-btn-tool"
                onClick={handleZoomIn}
                disabled={activeLoading || scale >= 2.5}
                title="Zoom In (+)"
              >
                <span>+</span>
              </button>

              <button
                type="button"
                className={`cpass-pdf-btn-tool ${isFitWidth ? 'active' : ''}`}
                onClick={handleFitWidthToggle}
                disabled={activeLoading}
                title="Fit document width to viewer (0)"
              >
                <span>⤢</span>
                <span className="cpass-pdf-btn-label">Fit Width</span>
              </button>

              <button
                type="button"
                className="cpass-pdf-btn-tool"
                onClick={handleRotate}
                disabled={activeLoading}
                title="Rotate 90 degrees clockwise"
              >
                <span>↺</span>
              </button>
            </div>
          </div>

          {/* Main Viewer Body: Optional Thumbnails Sidebar + Scrolling Pages Canvas */}
          <div className="cpass-pdf-main-area">
            {/* Thumbnails Sidebar (Collapsible, hidden by default) */}
            {showThumbnails && numPages > 0 && (
              <aside className="cpass-pdf-thumb-sidebar l1-no-print" aria-label="Page thumbnails">
                <div className="cpass-pdf-thumb-sidebar-title">Pages ({numPages})</div>
                <div className="cpass-pdf-thumb-scroll">
                  {pagesList.map((pageNum) => (
                    <PdfThumbnailItem
                      key={pageNum}
                      pdfDoc={pdfDoc}
                      pageNum={pageNum}
                      isActive={currentPage === pageNum}
                      onClick={() => scrollToPage(pageNum)}
                    />
                  ))}
                </div>
              </aside>
            )}

            {/* Scrolling Pages Canvas Viewport */}
            <div ref={scrollAreaRef} className="cpass-pdf-scroll-viewport">
              {loadingDoc && (
                <div className="cpass-pdf-status-screen">
                  <span className="cpass-pdf-spinner large" />
                  <h4>Loading PDF Document…</h4>
                  <p>Rendering high-resolution pages for review.</p>
                </div>
              )}

              {!loadingDoc && !docError && pdfDoc && (
                <div className="cpass-pdf-pages-stack">
                  {pagesList.map((pageNum) => (
                    <PdfPageItem
                      key={pageNum}
                      pdfDoc={pdfDoc}
                      pageNum={pageNum}
                      scale={scale}
                      rotation={rotation}
                      onVisible={setCurrentPage}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
