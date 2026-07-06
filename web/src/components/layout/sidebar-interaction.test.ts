import assert from 'node:assert/strict'
import test from 'node:test'
import { nextSidebarCollapsedForPointerDown } from './sidebar-interaction.ts'

test('expands the main sidebar when pointer starts inside it', () => {
  assert.equal(nextSidebarCollapsedForPointerDown({ isInsideSidebar: true }), false)
})

test('collapses the main sidebar when pointer starts outside it', () => {
  assert.equal(nextSidebarCollapsedForPointerDown({ isInsideSidebar: false }), true)
})
