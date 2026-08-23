import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Layout } from './components/Layout';
import { LandingPage } from './features/landing/LandingPage';
import { DashboardShell } from './features/dashboard/DashboardShell';
import { ProductsShell } from './features/products/ProductsShell';
import { UploadShell } from './features/upload/UploadShell';
import { SearchShell } from './features/search/SearchShell';
import { ReviewsShell } from './features/reviews/ReviewsShell';
import { JobsShell } from './features/jobs/JobsShell';
import { HealthShell } from './features/health/HealthShell';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 30000,
      gcTime: 10 * 60 * 1000,
      retry: 1,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* Public Editorial Landing Page */}
          <Route path="/" element={<LandingPage />} />

          {/* Main Console Platform Shell */}
          <Route element={<Layout />}>
            <Route path="dashboard" element={<DashboardShell />} />
            <Route path="catalog" element={<ProductsShell />} />
            <Route path="upload" element={<UploadShell />} />
            <Route path="jobs" element={<JobsShell />} />
            <Route path="search" element={<SearchShell />} />
            <Route path="reviews" element={<ReviewsShell />} />
            <Route path="health" element={<HealthShell />} />
            <Route path="settings" element={<Navigate to="/dashboard" replace />} />
          </Route>

          {/* Fallback to Home */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
