import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { MotionConfig } from 'motion/react'
import './index.css'
import App from './App.tsx'

/**
 * `reducedMotion="user"` is the one place the whole Framer side honours the OS setting. The CSS
 * `@media (prefers-reduced-motion)` block cannot reach the inline styles Framer writes, so
 * without this every `motion.*` component in the product animated regardless of the preference.
 * It reduces transform and layout animation and leaves opacity crossfades intact, which is the
 * calmer alternative rather than no feedback at all.
 */
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </MotionConfig>
  </StrictMode>,
)
