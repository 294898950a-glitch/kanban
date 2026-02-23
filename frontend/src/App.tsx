import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import NavRail from './components/NavRail'
import Dashboard from './pages/Dashboard'
import MetricsDoc from './pages/MetricsDoc'
import DetailPage from './pages/DetailPage'

export default function App() {
    return (
        <BrowserRouter>
            <div className="flex min-h-screen bg-gray-950 text-white">
                <NavRail />
                <main className="ml-60 flex-1 p-6 overflow-auto">
                    <Routes>
                        <Route path="/" element={<Dashboard />} />
                        <Route path="/docs" element={<MetricsDoc />} />
                        <Route path="/detail" element={<DetailPage />} />
                        <Route path="*" element={<Navigate to="/" replace />} />
                    </Routes>
                </main>
            </div>
        </BrowserRouter>
    )
}
