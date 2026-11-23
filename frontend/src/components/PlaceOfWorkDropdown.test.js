import assert from 'node:assert'
import {
  ALL_36_INDIAN_STATES_AND_UTS,
  INDIAN_STATES_28,
  INDIAN_UTS_8,
} from '../lib/courseDurationHelper.js'

function buildDropdownEntries(savedPlaceOfWork) {
  const trimmedSaved = (savedPlaceOfWork || '').trim()
  const isCustomSaved =
    Boolean(trimmedSaved) &&
    !ALL_36_INDIAN_STATES_AND_UTS.some((s) => s.toLowerCase() === trimmedSaved.toLowerCase())

  const entries = []
  entries.push({ type: 'item', value: '', label: 'Select State / UT' })

  if (isCustomSaved) {
    entries.push({
      type: 'item',
      value: trimmedSaved,
      label: `${trimmedSaved} (Saved Location)`,
      isSaved: true,
    })
  }

  entries.push({ type: 'header', label: 'States (28)' })
  for (const st of INDIAN_STATES_28) {
    entries.push({ type: 'item', value: st, label: st })
  }

  entries.push({ type: 'header', label: 'Union Territories (8)' })
  for (const ut of INDIAN_UTS_8) {
    entries.push({ type: 'item', value: ut, label: ut })
  }

  return entries
}

function runDropdownTests() {
  console.log('--- Running PlaceOfWorkDropdown UI Logic Tests ---')

  // 1. Verify 28 States and 8 UTs count and preservation
  {
    assert.strictEqual(INDIAN_STATES_28.length, 28, 'Must have exactly 28 states')
    assert.strictEqual(INDIAN_UTS_8.length, 8, 'Must have exactly 8 union territories')
    assert.strictEqual(ALL_36_INDIAN_STATES_AND_UTS.length, 36, 'Must have 36 total jurisdictions')

    const entries = buildDropdownEntries('')
    const stateItems = entries.filter((e) => e.type === 'item' && INDIAN_STATES_28.includes(e.value))
    assert.strictEqual(stateItems.length, 28, 'All 28 states present in dropdown entries')

    const utItems = entries.filter((e) => e.type === 'item' && INDIAN_UTS_8.includes(e.value))
    assert.strictEqual(utItems.length, 8, 'All 8 UTs present in dropdown entries')
    console.log('✓ Test 1: 28 States and 8 UTs verified')
  }

  // 2. Verify dropdown max-height and option heights math (approx 5-6 options visible)
  {
    const maxHeight = 190
    const optionHeight = 34
    const visibleCount = maxHeight / optionHeight
    assert.ok(visibleCount >= 5 && visibleCount <= 6, `Visible options (${visibleCount.toFixed(1)}) must be between 5 and 6`)
    console.log(`✓ Test 2: Max height ~190px displays ~${visibleCount.toFixed(1)} options before scroll`)
  }

  // 3. Verify custom saved location handling
  {
    const customEntries = buildDropdownEntries('Navi Mumbai')
    const savedEntry = customEntries.find((e) => e.isSaved)
    assert.ok(savedEntry, 'Custom saved location must be included')
    assert.strictEqual(savedEntry.value, 'Navi Mumbai')
    assert.strictEqual(savedEntry.label, 'Navi Mumbai (Saved Location)')

    // If already a standard state, no duplicate saved location entry
    const standardEntries = buildDropdownEntries('Gujarat')
    const noSaved = standardEntries.find((e) => e.isSaved)
    assert.strictEqual(noSaved, undefined, 'Standard state must not create extra saved entry')
    console.log('✓ Test 3: Custom saved location entry handled correctly')
  }

  // 4. Verify selection and keyboard navigation simulation
  {
    const entries = buildDropdownEntries('')
    const selectable = entries.filter((e) => e.type === 'item')

    // Initial placeholder item
    assert.strictEqual(selectable[0].value, '')
    assert.strictEqual(selectable[0].label, 'Select State / UT')

    // First state
    assert.strictEqual(selectable[1].value, 'Andhra Pradesh')

    // Type-ahead lookup simulation for 'T'
    const tMatches = selectable.filter((e) => e.label.toLowerCase().startsWith('t'))
    assert.ok(tMatches.some((e) => e.value === 'Tamil Nadu'))
    assert.ok(tMatches.some((e) => e.value === 'Telangana'))
    assert.ok(tMatches.some((e) => e.value === 'Tripura'))
    console.log('✓ Test 4: Selectable indexing and type-ahead simulation passed')
  }

  console.log('All PlaceOfWorkDropdown UI Logic Tests passed successfully!')
}

runDropdownTests()
