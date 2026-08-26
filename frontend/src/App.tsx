import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useWebSocketSync } from './hooks/useWebSocketSync'
import { ErrorToast } from './components/ErrorToast'
import { ConnectionBanner } from './components/ConnectionBanner'
import LandingPage from './pages/LandingPage'
import CreateRoomPage from './pages/CreateRoomPage'
import JoinRoomPage from './pages/JoinRoomPage'
import RoomPage from './pages/RoomPage'
import GamePage from './pages/GamePage'

/**
 * AppShell — mounts the WS sync hook once at the top level so it lives
 * for the full lifetime of the app, regardless of which route is active.
 */
function AppShell() {
  // Wire all WebSocket events → Zustand store. No render output.
  useWebSocketSync()

  return (
    <>
      <ConnectionBanner />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/create" element={<CreateRoomPage />} />
        <Route path="/join" element={<JoinRoomPage />} />
        <Route path="/room" element={<RoomPage />} />
        <Route path="/game" element={<GamePage />} />
        {/* Catch-all — redirect unknown paths to landing */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <ErrorToast />
    </>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  )
}
