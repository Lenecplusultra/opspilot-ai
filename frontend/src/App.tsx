import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import Approvals from "./pages/Approvals";
import Audit from "./pages/Audit";
import Board from "./pages/Board";
import Copilot from "./pages/Copilot";
import Login from "./pages/Login";

export default function App() {
  const { session, atLeast } = useAuth();
  if (!session) return <Login />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Board />} />
        <Route path="copilot" element={<Copilot />} />
        <Route path="approvals" element={<Approvals />} />
        <Route path="audit" element={atLeast("sre") ? <Audit /> : <Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
