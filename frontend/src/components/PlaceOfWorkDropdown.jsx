import React, { useState, useRef, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'
import {
  ALL_36_INDIAN_STATES_AND_UTS,
  INDIAN_STATES_28,
  INDIAN_UTS_8,
} from '../lib/courseDurationHelper'

/**
 * PlaceOfWorkDropdown
 *
 * Portal-anchored custom dropdown for Place of Work (State / UT):
 * - 38px height matching form controls exactly
 * - Rendered via React portal directly to document.body with fixed positioning
 *   to completely prevent table container overflow, scrollbars, or layout displacement
 * - Strictly matches the input's width and position
 * - Max height capped at ~190px displaying 5-6 options with slim scrollbar
 * - Grouped options (States (28) and Union Territories (8))
 * - Highlighted active selection with checkmark
 * - Keyboard navigation (arrows, enter, escape, type-ahead)
 * - Auto-scroll selected item into view on open
 */
export default function PlaceOfWorkDropdown({
  value,
  savedPlaceOfWork,
  onChange,
  disabled = false,
  placeholder = 'Select State / UT',
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0, width: 0, placement: 'bottom' })

  const containerRef = useRef(null)
  const menuRef = useRef(null)
  const triggerRef = useRef(null)
  const searchTimeoutRef = useRef(null)
  const searchBufferRef = useRef('')

  // Determine if there is a custom saved location not in the standard 36 list
  const trimmedSaved = (savedPlaceOfWork || '').trim()
  const isCustomSaved =
    Boolean(trimmedSaved) &&
    !ALL_36_INDIAN_STATES_AND_UTS.some((s) => s.toLowerCase() === trimmedSaved.toLowerCase())

  // Build the complete list of entries (headers and selectable options)
  const entries = []
  // 1. Placeholder / Clear option
  entries.push({ type: 'item', value: '', label: placeholder })

  // 2. Saved custom location if present
  if (isCustomSaved) {
    entries.push({
      type: 'item',
      value: trimmedSaved,
      label: `${trimmedSaved} (Saved Location)`,
      isSaved: true,
    })
  }

  // 3. States group (28)
  entries.push({ type: 'header', label: 'States (28)' })
  for (const st of INDIAN_STATES_28) {
    entries.push({ type: 'item', value: st, label: st })
  }

  // 4. Union Territories group (8)
  entries.push({ type: 'header', label: 'Union Territories (8)' })
  for (const ut of INDIAN_UTS_8) {
    entries.push({ type: 'item', value: ut, label: ut })
  }

  // Selectable items only for navigation indexing
  const selectableIndices = entries
    .map((e, idx) => (e.type === 'item' ? idx : null))
    .filter((idx) => idx !== null)

  // Resolve display label
  let displayLabel = ''
  if (value) {
    const found = ALL_36_INDIAN_STATES_AND_UTS.find(
      (s) => s.toLowerCase() === String(value).trim().toLowerCase()
    )
    if (found) {
      displayLabel = found
    } else if (isCustomSaved && value.toLowerCase() === trimmedSaved.toLowerCase()) {
      displayLabel = `${trimmedSaved} (Saved Location)`
    } else {
      displayLabel = value
    }
  }

  // Calculate fixed popup position anchored to the trigger input
  const updatePosition = useCallback(() => {
    if (!triggerRef.current) return
    const rect = triggerRef.current.getBoundingClientRect()

    // If trigger element has scrolled off screen, close dropdown
    if (rect.bottom < 0 || rect.top > window.innerHeight) {
      setIsOpen(false)
      return
    }

    const dropdownHeight = 194 // ~190px max-height + 4px offset
    const spaceBelow = window.innerHeight - rect.bottom
    const fitsBelow = spaceBelow >= 120 || spaceBelow >= rect.top

    let top = 0
    let placement = 'bottom'
    if (fitsBelow) {
      top = rect.bottom + 4
      placement = 'bottom'
    } else {
      top = Math.max(8, rect.top - dropdownHeight - 4)
      placement = 'top'
    }

    const width = rect.width
    let left = rect.left
    if (left + width > window.innerWidth - 8) {
      left = Math.max(8, window.innerWidth - width - 8)
    }

    setMenuPosition({
      top,
      left,
      width,
      placement,
    })
  }, [])

  // Reposition on open, scroll (any parent container), and window resize
  useEffect(() => {
    if (!isOpen) return

    updatePosition()

    const handleScrollOrResize = () => {
      updatePosition()
    }

    window.addEventListener('resize', handleScrollOrResize)
    window.addEventListener('scroll', handleScrollOrResize, true)

    return () => {
      window.removeEventListener('resize', handleScrollOrResize)
      window.removeEventListener('scroll', handleScrollOrResize, true)
    }
  }, [isOpen, updatePosition])

  // Close dropdown when clicking outside (checks both container and portal menu)
  useEffect(() => {
    if (!isOpen) return

    function handleOutsideClick(e) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target) &&
        menuRef.current &&
        !menuRef.current.contains(e.target)
      ) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleOutsideClick, true)
    document.addEventListener('touchstart', handleOutsideClick, true)
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick, true)
      document.removeEventListener('touchstart', handleOutsideClick, true)
    }
  }, [isOpen])

  // Scroll selected or highlighted item into view within the 190px container
  const scrollToItem = useCallback((idx) => {
    if (!menuRef.current || idx < 0) return
    const itemEl = menuRef.current.querySelector(`[data-index="${idx}"]`)
    if (itemEl) {
      itemEl.scrollIntoView({ block: 'nearest' })
    }
  }, [])

  // When opening, initialize highlighted index to current selected item and scroll to it
  useEffect(() => {
    if (isOpen) {
      const selectedEntryIdx = entries.findIndex(
        (e) => e.type === 'item' && e.value.toLowerCase() === (value || '').trim().toLowerCase()
      )
      const targetIdx = selectedEntryIdx >= 0 ? selectedEntryIdx : 0
      setHighlightedIndex(targetIdx)
      requestAnimationFrame(() => scrollToItem(targetIdx))
    } else {
      setHighlightedIndex(-1)
      searchBufferRef.current = ''
    }
  }, [isOpen, value, scrollToItem])

  const selectOption = useCallback(
    (val) => {
      setIsOpen(false)
      if (typeof onChange === 'function') {
        onChange(val)
      }
      if (triggerRef.current) {
        triggerRef.current.focus()
      }
    },
    [onChange]
  )

  const handleTriggerClick = () => {
    if (disabled) return
    setIsOpen((prev) => !prev)
  }

  const handleKeyDown = (e) => {
    if (disabled) return

    // Open on Enter, Space, Down, or Up if closed
    if (!isOpen) {
      if (['Enter', ' ', 'ArrowDown', 'ArrowUp'].includes(e.key)) {
        e.preventDefault()
        setIsOpen(true)
      }
      return
    }

    // Handlers when open
    if (e.key === 'Escape') {
      e.preventDefault()
      setIsOpen(false)
      if (triggerRef.current) triggerRef.current.focus()
      return
    }

    if (e.key === 'Tab') {
      setIsOpen(false)
      return
    }

    if (e.key === 'Enter') {
      e.preventDefault()
      if (highlightedIndex >= 0 && entries[highlightedIndex]?.type === 'item') {
        selectOption(entries[highlightedIndex].value)
      }
      return
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      const currentPos = selectableIndices.indexOf(highlightedIndex)
      const nextPos = currentPos < selectableIndices.length - 1 ? currentPos + 1 : 0
      const nextIdx = selectableIndices[nextPos]
      setHighlightedIndex(nextIdx)
      scrollToItem(nextIdx)
      return
    }

    if (e.key === 'ArrowUp') {
      e.preventDefault()
      const currentPos = selectableIndices.indexOf(highlightedIndex)
      const prevPos = currentPos > 0 ? currentPos - 1 : selectableIndices.length - 1
      const prevIdx = selectableIndices[prevPos]
      setHighlightedIndex(prevIdx)
      scrollToItem(prevIdx)
      return
    }

    // Type-ahead jump: match first letter
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault()
      clearTimeout(searchTimeoutRef.current)
      searchBufferRef.current += e.key.toLowerCase()
      searchTimeoutRef.current = setTimeout(() => {
        searchBufferRef.current = ''
      }, 500)

      const query = searchBufferRef.current
      const matchIdx = entries.findIndex(
        (entry) => entry.type === 'item' && entry.label.toLowerCase().startsWith(query)
      )
      if (matchIdx >= 0) {
        setHighlightedIndex(matchIdx)
        scrollToItem(matchIdx)
      }
    }
  }

  return (
    <div className="l1-state-dropdown-container" ref={containerRef}>
      <button
        ref={triggerRef}
        type="button"
        className={`l1-state-dropdown-trigger ${isOpen ? 'open' : ''}`}
        onClick={handleTriggerClick}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        title={displayLabel || placeholder}
      >
        <span className={`l1-state-dropdown-trigger-text ${!value ? 'placeholder' : ''}`}>
          {displayLabel || placeholder}
        </span>
        <svg
          className={`l1-state-dropdown-chevron ${isOpen ? 'open' : ''}`}
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {/* Hidden input for HTML form compliance */}
      <input type="hidden" name="place_of_work" value={value || ''} />

      {isOpen && typeof document !== 'undefined' &&
        createPortal(
          <div
            ref={menuRef}
            className={`l1-state-dropdown-menu ${menuPosition.placement}`}
            style={{
              position: 'fixed',
              top: `${menuPosition.top}px`,
              left: `${menuPosition.left}px`,
              width: `${menuPosition.width}px`,
              zIndex: 99999,
            }}
            role="listbox"
            tabIndex={-1}
            onKeyDown={handleKeyDown}
          >
            {entries.map((entry, idx) => {
              if (entry.type === 'header') {
                return (
                  <div key={`header-${entry.label}`} className="l1-state-dropdown-group-header">
                    {entry.label}
                  </div>
                )
              }

              const isSelected =
                entry.value.toLowerCase() === (value || '').trim().toLowerCase()
              const isHighlighted = idx === highlightedIndex

              return (
                <div
                  key={`opt-${entry.value || 'empty'}-${idx}`}
                  data-index={idx}
                  role="option"
                  aria-selected={isSelected}
                  className={`l1-state-dropdown-option ${isSelected ? 'selected' : ''} ${
                    isHighlighted ? 'highlighted' : ''
                  }`}
                  onClick={() => selectOption(entry.value)}
                  onMouseEnter={() => setHighlightedIndex(idx)}
                >
                  <span className="l1-state-dropdown-option-label">{entry.label}</span>
                  {isSelected && <span className="l1-state-dropdown-check">✓</span>}
                </div>
              )
            })}
          </div>,
          document.body
        )}
    </div>
  )
}
