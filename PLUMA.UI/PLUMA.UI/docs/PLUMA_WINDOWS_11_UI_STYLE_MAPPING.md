# PLUMA — Windows 11 / WinUI 3 UI Style Mapping

This file maps each PLUMA UI surface to the **closest official Windows 11 Fluent / WinUI 3 design pattern or control name**.

## Naming rule

- **Exact** = Windows/WinUI has a direct control or shell surface for this.
- **Compose** = Windows has no single control; build it from official Fluent primitives.
- **Do not fake a Windows control name** where none exists.

---

# Global Windows 11 Design Language

| Area | Exact Windows / WinUI name |
|---|---|
| Design language | **Fluent Design System for Windows 11** |
| UI framework reference | **WinUI 3 / Windows App SDK** |
| Primary window backdrop | **Mica** |
| Alternate base backdrop | **Mica Alt** |
| Transient / light-dismiss material | **Acrylic** / **Background Acrylic** |
| Modal dimming layer | **Smoke** |
| Main app shell | **TitleBar + NavigationView + Frame** |
| Main font | **Segoe UI Variable** |
| UI icon font | **Segoe Fluent Icons** |
| Normal text weight | **Regular 400** |
| Heading weight | **Semibold 600** |
| In-page corner radius | **ControlCornerRadius — 4 px** |
| Overlay / dialog / flyout radius | **OverlayCornerRadius — 8 px** |
| Standard card fill | **CardBackgroundFillColorDefaultBrush** |
| Standard card border | **CardStrokeColorDefaultBrush** |
| Standard content layer | **LayerFillColorDefaultBrush** |
| Small status dot / notification badge | **InfoBadge** |
| Non-blocking inline status | **InfoBar** |
| Blocking modal | **ContentDialog** |
| Lightweight contextual popup | **Flyout** |
| Rich contextual callout | **TeachingTip** |
| Small hover callout | **ToolTip** |
| Search field | **AutoSuggestBox** |
| Indeterminate progress | **ProgressRing** |
| Determinate progress | **ProgressBar** |
| General animated visual | **AnimatedVisualPlayer** |
| State-driven animated icon | **AnimatedIcon** |
| Windows shell notification | **App notification** (`AppNotificationManager`) |

### Important material rule

- Use **Mica** for long-lived window surfaces.
- Use **Acrylic** for transient surfaces such as flyouts and light-dismiss overlays.
- Use **Smoke** behind blocking modal dialogs.
- Do not put Acrylic over Acrylic.
- Do not turn the whole app into generic “glassmorphism”.

---

# PLUMA Surface → Windows 11 Mapping

## Full-Screen Surfaces

### 1. Dashboard
**Windows design name:** **Modern WinUI app shell / App silhouette**  
**Exact controls:** `TitleBar` + `NavigationView` + `Frame`  
**Material:** `Mica`  
**Inside the page:** `TextBox` or `AutoSuggestBox`, `ListView`, `InfoBadge`, `ProgressRing`, Fluent card pattern  
**Match:** **Compose**

Recommended visual identity: a normal first-party-style WinUI 3 desktop app, not a custom dashboard theme.

---

### 2. Settings
**Windows design name:** **App Settings page**  
**Exact controls:** `SettingsCard` + `SettingsExpander` from **Windows Community Toolkit**  
**Supporting controls:** `ToggleSwitch`, `ComboBox`, `TextBox`, `NumberBox`, `Button`  
**Material:** `Mica` base + standard layer/card fills  
**Match:** **Exact Windows settings pattern**

This is the closest way to make PLUMA look like modern Windows Settings.

---

### 3. History / Activity Ledger
**Windows design name:** **List/details pattern**  
**Exact controls:** `ListView` + `AutoSuggestBox` for search  
**Optional:** `Expander` or a details pane for expanded records  
**Material:** `Mica` + Fluent card/list backplates  
**Match:** **Compose from native pattern**

---

# Floating Popup Surfaces

> WinUI `Flyout` is normally attached to an app window. If PLUMA needs overlays that appear independently over the desktop, copy the **visual treatment** of a Windows Flyout using a lightweight top-level window with Acrylic. Do not pretend there is a native “desktop flyout” control.

### 4. Task Running Popup
**Windows design name:** **Transient Flyout / progress flyout**  
**Exact primitives:** `Flyout` + `ProgressRing` + `TextBlock`  
**Material:** **Acrylic**  
**Geometry:** `OverlayCornerRadius`  
**Match:** **Compose**

---

### 5. Step Progress Popup
**Windows design name:** **Progress Flyout**  
**Exact primitives:** `Flyout` + `ProgressRing` or `ProgressBar`  
**Material:** **Acrylic**  
**Match:** **Compose**

Use `ProgressBar` when Step N of M is known; use `ProgressRing` when duration is unknown.

---

### 6. Route Badge Popup
**Windows design name:** **Compact Acrylic Flyout**  
**Exact primitives:** `Flyout` + `TextBlock`  
**Material:** **Acrylic**  
**Match:** **Compose**

There is **no native WinUI arbitrary-text “badge” control**. `InfoBadge` is for a dot, icon, or number—not labels such as FAST / SMART / DEEP / SCREEN.

---

### 7. Tool Call Card
**Windows design name:** **Fluent Card pattern**  
**Exact primitives:** `Border` / item container using:
- `CardBackgroundFillColorDefaultBrush`
- `CardStrokeColorDefaultBrush`
- `ControlCornerRadius` or `OverlayCornerRadius`

**Supporting controls:** `TextBlock`, `ProgressRing`, status/risk indicator  
**Match:** **Exact Fluent card pattern, composed control**

---

### 8. Tool Result Card
**Windows design name:** **Fluent Card pattern + result status**  
**Exact primitives:** same Fluent card resources as Tool Call Card  
**Status component:** `InfoBadge` for icon/dot status, or small status icon + text  
**Match:** **Compose**

For a larger success/error message, use an `InfoBar` instead of inventing a custom alert style.

---

### 9. Rollback Popup
**Windows design name:** **Progress Flyout**  
**Exact primitives:** `Flyout` + `ProgressBar` / `ProgressRing` + `ListView` or stacked text rows  
**Material:** **Acrylic**  
**Match:** **Compose**

If rollback must block all interaction, promote this surface to a `ContentDialog`.

---

### 10. Conflict Alert Popup
**Windows design name:** **ContentDialog**  
**Exact controls:** `ContentDialog` + `Button` / `HyperlinkButton`  
**Material:** dialog surface + **Smoke** behind it  
**Match:** **Exact**

Because manual resolution is required, this should feel like a Windows blocking decision dialog, not a casual toast.

---

# Voice / STT Surfaces

### 11. Voice Listening Animation
**Windows design name:** **Fluent Motion visual**  
**Exact controls:** `AnimatedVisualPlayer`  
**Optional icon state:** `AnimatedIcon` for microphone state changes  
**Surface:** Acrylic floating overlay if detached from the main window  
**Match:** **Compose**

Use `AnimatedVisualPlayer` for the waveform/pulse itself. `AnimatedIcon` is only for an icon changing with visual state.

---

### 12. Live Transcription Overlay
**Windows design name:** **Acrylic Flyout overlay**  
**Exact primitives:** `Flyout` visual treatment + `TextBlock` / `RichTextBlock`  
**Material:** **Acrylic**  
**Match:** **Compose**

There is no dedicated Windows “live transcription overlay” WinUI control.

---

### 13. Voice Committed Banner
**Windows design name:** **InfoBar**  
**Exact control:** `InfoBar`  
**Severity:** Informational / success depending on state  
**Match:** **Exact**

If it must float outside the app instead of occupying layout space, use the same content inside an Acrylic flyout-style overlay.

---

### 14. Voice Silence Timeout Indicator
**Windows design name:** **Determinate ProgressBar**  
**Exact control:** `ProgressBar`  
**Container:** existing voice Flyout / Acrylic overlay  
**Match:** **Exact progress control inside composed surface**

---

# OCR / Perception Surfaces

### 15. Screen Capture Flash
**Windows design name:** **Fluent Motion feedback**  
**Exact implementation family:** Windows Composition / XAML animation  
**Typical primitive:** animated `Border` / opacity animation  
**Match:** **Compose — no native named capture-flash control**

Keep it extremely brief and subtle.

---

### 16. OCR Match Indicator
**Windows design name:** **Focus visual + contextual callout**  
**Exact visual references:** focus rectangle / highlight + `ToolTip`- or `TeachingTip`-style callout  
**Material for callout:** Acrylic  
**Match:** **Compose**

Do not make the OCR target box look like a gaming HUD. Windows-style focus/highlight geometry will integrate better.

---

### 17. Post-Click Verify Indicator
**Windows design name:** **InfoBar with Success / Error severity**  
**Exact control:** `InfoBar`  
**Match:** **Exact**

For a tiny overlay version, reproduce the same status icon/text hierarchy inside an Acrylic flyout.

---

# Confirmation / Policy Surfaces

### 18. Risk Approval Dialog
**Windows design name:** **ContentDialog / confirmation dialog**  
**Exact control:** `ContentDialog`  
**Buttons:** primary `Button` + secondary/default action  
**Material:** dialog surface + **Smoke**  
**Match:** **Exact**

This is the correct Windows pattern for explicit approval before a consequential action.

---

### 19. Policy Block Notice
**Windows design name:** **InfoBar**  
**Exact control:** `InfoBar`  
**Severity:** Warning or Error  
**Match:** **Exact**

Use this instead of a custom red alert card.

---

# STOP / Cancellation Surfaces

### 20. Cancellation Animation
**Windows design name:** **Progress overlay / progress flyout**  
**Exact primitives:** `ProgressRing` + `TextBlock`  
**Material:** Acrylic if floating  
**Motion:** Fluent Motion / `AnimatedVisualPlayer` only if a custom animation is needed  
**Match:** **Compose**

---

### 21. Worker Termination Flash
**Windows design name:** **Transient status notification**  
**Preferred in-app control:** `InfoBar`  
**Preferred floating visual:** compact Acrylic flyout-style surface  
**Match:** **Compose**

Avoid using a Windows App Notification for every internal worker termination unless the user genuinely needs a shell-level notification.

---

# Status / Message Surfaces

### 22. Live Message Feed
**Windows design name:** **ListView / activity list**  
**Exact controls:** `ListView` + `TextBlock`  
**Optional:** `ScrollViewer` behavior is normally handled by the list  
**Visual pattern:** Fluent list rows or Card pattern  
**Match:** **Exact primitives**

---

### 23. Core Health Indicator
**Windows design name:** **InfoBadge + status text**  
**Exact control:** `InfoBadge` for the dot/icon  
**Supporting control:** `TextBlock`  
**Match:** **Exact primitives**

Use system success/error theme resources rather than hard-coded neon green/red.

---

### 24. Toast Notification
**Current Windows name:** **App notification**  
**Exact Windows API family:** `AppNotificationManager` / `AppNotificationBuilder`  
**Rendered by:** Windows shell / Notification Center  
**Match:** **Exact**

Microsoft is replacing the older term **toast notification** with **app notification** in current Windows App SDK documentation.

---

### 25. Critical Error Dialog
**Windows design name:** **ContentDialog**  
**Exact control:** `ContentDialog`  
**Material:** dialog surface + **Smoke**  
**Supporting controls:** `Button`, optional `Expander` for technical details  
**Match:** **Exact**

Use a clear primary recovery action such as “Restart core”.

---

# Onboarding Surface

### 26. Setup Wizard
**Windows design name:** **Sequential task flow / wizard pattern**  
**WinUI note:** there is **no built-in WinUI 3 `Wizard` control**  
**Exact primitives:** `Frame` + `Page` + `Button` + `ProgressBar` + checklist/list controls  
**Motion:** standard navigation transitions  
**Material:** Mica  
**Match:** **Compose**

Visually, keep it closer to Windows first-run / Settings setup screens than to a web onboarding carousel.

---

# Recommended PLUMA Design Stack

If the goal is for PLUMA to feel as though it belongs in Windows 11, use this hierarchy:

1. **WinUI 3 / Windows App SDK visual language**
2. **Mica** for the main window
3. **Acrylic** only for transient overlays
4. **Smoke** for blocking dialogs
5. **Segoe UI Variable**
6. **Segoe Fluent Icons**
7. **NavigationView + TitleBar** for the app shell
8. **SettingsCard / SettingsExpander** for Settings
9. **ListView** for history and activity
10. **InfoBar** for non-blocking status
11. **ContentDialog** for approval/conflict/critical errors
12. **Flyout** visual treatment for compact overlays
13. **ProgressRing / ProgressBar** for work state
14. **Fluent Card pattern** for tool cards
15. **App notification** for actual Windows shell notifications
16. **4 px control radius / 8 px overlay radius**
17. Use Windows theme resources instead of manually chosen “cool” colors

---

# Terms to Avoid in the PLUMA Design Spec

These are not the correct names for the Windows 11 look:

- “Glassmorphism UI”
- “Frosted glass dashboard”
- “Cyberpunk Windows”
- “Neumorphism”
- “Modern AI gradient UI”
- “Floating glass cards everywhere”

Use the actual vocabulary instead:

**Fluent Design, WinUI 3, Mica, Acrylic, Smoke, NavigationView, ContentDialog, InfoBar, Flyout, Fluent Card pattern, Segoe UI Variable, Segoe Fluent Icons.**

---

# Official Microsoft Reference Pages

- Windows app structure: https://learn.microsoft.com/windows/apps/develop/ui/windows-app-sdk-app-structure
- Materials: https://learn.microsoft.com/windows/apps/design/signature-experiences/materials
- Mica: https://learn.microsoft.com/windows/apps/design/style/mica
- Acrylic: https://learn.microsoft.com/windows/apps/design/style/acrylic
- Geometry: https://learn.microsoft.com/windows/apps/design/signature-experiences/geometry
- Typography: https://learn.microsoft.com/windows/apps/design/signature-experiences/typography
- NavigationView: https://learn.microsoft.com/windows/apps/design/controls/navigationview
- App settings guidance: https://learn.microsoft.com/windows/apps/design/app-settings/guidelines-for-app-settings
- InfoBar: https://learn.microsoft.com/windows/apps/develop/ui/controls/infobar
- InfoBadge: https://learn.microsoft.com/windows/apps/develop/ui/controls/info-badge
- Dialogs and flyouts: https://learn.microsoft.com/windows/apps/develop/ui/controls/dialogs-and-flyouts/
- TeachingTip: https://learn.microsoft.com/windows/apps/develop/ui/controls/dialogs-and-flyouts/teaching-tip
- Progress controls: https://learn.microsoft.com/windows/apps/develop/ui/controls/progress-controls
- AnimatedIcon: https://learn.microsoft.com/windows/apps/develop/ui/controls/animated-icon
- App notifications: https://learn.microsoft.com/windows/apps/develop/notifications/
