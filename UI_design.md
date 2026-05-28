# UI Design System: fypd Dashboard

The fypd dashboard is the orchestration layer of the application. The design philosophy is centered around creating a **premium, Apple-inspired glassmorphic aesthetic** that feels dynamic, responsive, and professional. 

## 1. Technology Stack
- **Framework:** React + Vite
- **Styling:** Tailwind CSS (for utility-first rapid styling)
- **Animations:** Framer Motion (for fluid, physics-based micro-interactions)

## 2. Core Aesthetic Principles
- **Glassmorphism:** The UI utilizes translucent panels with background blur (`backdrop-blur`) layered over subtle gradient backgrounds. This creates depth and hierarchy without heavy drop shadows.
- **Dark Mode Native:** The application is designed primarily for a dark aesthetic to reduce eye strain for creators during long editing sessions and to make the brightly colored video previews "pop".
- **Dynamic & Alive:** The interface shouldn't feel static. Hover states, loading transitions, and job processing updates should utilize smooth micro-animations.

## 3. Color Palette
- **Background:** Deep, rich dark gradients (e.g., `#0f172a` to `#020617` — Slate 900 to 950).
- **Surface Panels:** Translucent white/slate overlays (`rgba(255, 255, 255, 0.05)`) with thin borders (`rgba(255, 255, 255, 0.1)`).
- **Accents:** 
  - *Primary:* Vibrant iOS-style blue (`#0A84FF`) for primary actions.
  - *Success:* Emerald green (`#34C759`) for completed jobs and active states.
  - *Warning/Error:* Ruby red (`#FF453A`) for failed jobs or destructive actions.
- **Text:** High-contrast white (`#F8FAFC`) for primary headings, and muted slate (`#94A3B8`) for secondary text and metadata.

## 4. Typography
- **Font Family:** `Inter`, `SF Pro`, or `Roboto`. The font should be a highly legible, modern sans-serif.
- **Hierarchy:**
  - **H1 (Dashboard Titles):** Bold, clean, occasionally utilizing subtle gradient text clips.
  - **Body Text:** Regular weight, optimized for readability.
  - **Monospace/Data:** Used for job IDs, timestamps, and log outputs to differentiate system data from UI text.

## 5. Micro-Animations (Framer Motion)
- **Panel Entrances:** Staggered fade-and-slide-up animations when the dashboard loads or new jobs are added.
- **Button Interactions:** Scale down slightly on press (`scale: 0.97`) and brighten on hover.
- **Progress Indicators:** Smooth, easing transitions on progress bars instead of harsh jumps. Loading spinners should feel fluid.

## 6. Layout & Composition
- **Sidebar/Navigation:** Collapsible or slim side navigation for switching between the main Dashboard, System Configuration (API keys), and Logs.
- **Job Panels:** Widescreen "Parent" cards representing the source video, containing nested "Child" cards representing the individual vertical shorts being generated. 
- **Responsive Grid:** The dashboard must scale gracefully from the confined Tauri desktop window down to standard tablet dimensions.

## 7. Component Library Guidelines
- **Inputs & Forms:** Rounded corners (e.g., `rounded-xl` or `rounded-2xl`), subtle internal padding, and focus rings that utilize the primary accent color with a soft glow.
- **Modals:** Used for the "Cinema Player" review feature. Modals must dim the background completely (`bg-black/60`) and blur the underlying dashboard.
- **Toasts/Notifications:** Floating, pill-shaped notifications at the bottom or top right for quick status updates (e.g., "API Keys Saved", "Job Queued").
