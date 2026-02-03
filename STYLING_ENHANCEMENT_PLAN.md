# Styling Enhancement Plan (Streamlit Frontend)

Date: 2026-02-02

This document defines a comprehensive, step-by-step styling and UX enhancement plan for the Streamlit app. It includes a global design system, page-by-page upgrades, table UX improvements (search/sort/pagination), export enhancements, and QA criteria.

---

## 1) Goals

- Professional pharmacy-grade UI with clear hierarchy and fast workflows.
- Consistent styling across pages (cards, badges, buttons, inputs, tables).
- Strong data table usability: search, filter, sort, pagination, export.
- Improved dark mode styling and accessibility.
- Export outputs (CSV/Excel/PDF) are consistent and reliable.

---

## 2) Design System (Global)

### 2.1 Colors
- Primary: `#1B6EF3`
- Primary Dark: `#144BA6`
- Success: `#0F9D58`
- Warning: `#F4B400`
- Error: `#DB4437`
- Info: `#1A73E8`
- Background (light): `#F7F8FB`
- Surface (light cards): `#FFFFFF`
- Text primary: `#1F2937`
- Text secondary: `#6B7280`

Dark mode:
- Background: `#0F1115`
- Surface: `#151A24`
- Border: `#2A3244`
- Text: `#E6E6E6`

### 2.2 Typography
- Title: 20–24px, bold
- Section headers: 16–18px, semi-bold
- Body: 13–14px
- Table: 12–13px

### 2.3 Spacing & Layout
- Base spacing: 8px grid
- Card padding: 16–20px
- Section spacing: 24px
- Form controls aligned in 2 columns where possible

### 2.4 Components
- **Card**: rounded corners, subtle shadow, padding 16px
- **Badge**: rounded pill, color-coded by status
- **Alert**: colored left border
- **Action bar**: horizontal group of buttons aligned right

---

## 3) Global UI Enhancements

- Add `global.css` injection (Streamlit markdown) for:
  - Background colors
  - Sidebar styling
  - Button styles
  - Input field styles
  - Table header and zebra row styles
- Add helper functions:
  - `render_card(title, body)`
  - `render_badge(status)`
  - `render_section_header(title)`
- Apply consistent typography in all headings.

---

## 4) Page-by-Page Styling Enhancements

### 4.1 Login
- Centered login card.
- Clear feedback colors for success/error.
- Optional logo area.

### 4.2 Session Setup
- Two-column form layout.
- Required fields marked with asterisks and hints.
- Summary panel with session preview.

### 4.3 Scan & Count
- Large scan input with focus ring.
- Scan result card as two-column grid of label/value rows.
- Color-coded status badge (Valid/Near/Expired/Unknown).
- Quick actions row (Copy GTIN, Show SFDA, Clear).
- Count input area grouped in a card.

### 4.4 Inventory Lines Table
- Table header styled + sticky header.
- Zebra rows and highlight on hover.
- Search bar with inline filters.
- Sorting dropdown + quick sort buttons.
- Pagination controls (page size, next/prev).
- Export current view toolbar.

### 4.5 Review & Reconcile
- KPI cards row (total lines, unique items, warnings).
- Aggregated and detailed sections visually separated.
- Warnings list with colored badges.
- Bulk edit panel styled with separators.

### 4.6 Finalize & Reports
- Report summary panel.
- Export section with grouped buttons.
- Warnings section emphasized.
- Finalize button styled as destructive.

### 4.7 Audit & Logs
- Toolbar with search/filter.
- Badge for action types (login, add, delete, finalize).
- Export buttons aligned right.

### 4.8 Settings
- Group settings into sections.
- Apply toggle-style visuals.
- Inline help notes for advanced options.

---

## 5) Table UX Enhancements

- Search across all columns.
- Filter by:
  - Status
  - Date range
  - GTIN
- Sorting:
  - Default by timestamp desc
  - User-selectable sort field + order
- Pagination:
  - Page size: 25/50/100
  - Page selector
- Export:
  - CSV/Excel for full dataset
  - CSV/Excel for filtered view

---

## 6) Export Enhancements

- Ensure Excel exports include metadata sheet.
- PDF styling refinements:
  - Consistent headers
  - Branded footer
  - Improved spacing for readability
- Provide export confirmation banner with file path.

---

## 7) Dark Mode Improvements

- Extend CSS to style tables, cards, and badges.
- Ensure contrast ratios pass accessibility thresholds.
- Verify icons visible in dark background.

---

## 8) QA Checklist

- Layout consistent on 1366px and mobile width.
- Dark mode readability verified.
- All tables searchable, sortable, paginated.
- All export buttons generate files without errors.
- Scan workflow remains fast (Enter parse → Enter add).

---

## 9) Execution Phases

1) Build global CSS + helpers (design system)
2) Update Scan & Count UI
3) Upgrade Inventory table UX
4) Polish Review/Finalize/Audit
5) Improve exports + QA

---

## 10) Next Steps

- Decide final color palette and typography.
- Approve styling scope for each page.
- Start implementing global CSS and component helpers.
