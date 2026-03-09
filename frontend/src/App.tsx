import { useState } from 'react';
import LoginForm from './components/LoginForm';
import Dashboard from './components/Dashboard';

function App() {
  const [userId, setUserId] = useState<string | null>(() => {
    return localStorage.getItem('userId');
  });

  const handleLogin = (id: string) => {
    setUserId(id);
  };

  const handleLogout = () => {
    localStorage.removeItem('userId');
    localStorage.removeItem('userName');
    setUserId(null);
  };

  if (!userId) {
    return <LoginForm onLogin={handleLogin} />;
  }

  return <Dashboard userId={userId} onLogout={handleLogout} />;
}

export default App;
