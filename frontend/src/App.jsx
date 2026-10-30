import {useEffect,useState} from 'react';
import {Routes,Route,Navigate,useLocation} from 'react-router-dom';
import Atmosphere from './components/Atmosphere';
import Login from './pages/Login';
import Workspace from './layouts/Workspace';
import {Documents,Assistant} from './pages/Pages';
import {RoleDashboard,Employees,Analytics,BatchQuestions} from './pages/CompanyPages';
import {api} from './services/api';
export default function App(){
 const {pathname}=useLocation();
 const [arriving,setArriving]=useState(false);
 useEffect(()=>{if(!arriving)return;const timer=setTimeout(()=>setArriving(false),800);return()=>clearTimeout(timer);},[arriving]);
 useEffect(()=>{window.scrollTo(0,0);},[pathname]);
 const [user,setUser]=useState(null),[loading,setLoading]=useState(true),[error,setError]=useState('');
 useEffect(()=>{const expired=()=>{setUser(null);setError('Your session expired. Please sign in again.');};window.addEventListener('eka:unauthorized',expired);return()=>window.removeEventListener('eka:unauthorized',expired);},[]);
 useEffect(()=>{api('/auth/me').then(setUser).catch(e=>{if(e.status!==401)setError('Cannot reach the backend. Start FastAPI and refresh.');}).finally(()=>setLoading(false));},[]);
 async function logout(){try{await api('/auth/logout',{method:'POST'});setUser(null);setError('');}catch(e){setError(e.message);}}
 return <div className={`${user?'authenticated':'unauthenticated'} ${arriving?'auth-arriving':''}`}><Atmosphere/>{arriving&&<div className="auth-transition" aria-hidden="true"/>}{loading?<div className="loading" role="status">Opening your workspace...</div>:<>{error&&!user&&<div className="connection-error" role="alert">{error}</div>}<Routes><Route path="/login" element={user?<Navigate to="/" replace/>:<Login onLogin={u=>{setArriving(true);setUser(u);setError('');}}/>}/><Route element={user?<Workspace user={user} onLogout={logout} error={error}/>:<Navigate to="/login" replace/>}><Route index element={<RoleDashboard/>}/><Route path="documents" element={user?.role==='admin'?<Documents/>:<Navigate to="/" replace/>}/><Route path="employees" element={user?.role==='admin'?<Employees/>:<Navigate to="/" replace/>}/><Route path="analytics" element={user?.role==='admin'?<Analytics/>:<Navigate to="/" replace/>}/><Route path="assistant" element={user?.role==='employee'?<Assistant/>:<Navigate to="/" replace/>}/><Route path="batch" element={user?.role==='employee'?<BatchQuestions/>:<Navigate to="/" replace/>}/><Route path="reports" element={user?.role==='employee'?<Analytics personal/>:<Navigate to="/" replace/>}/></Route><Route path="*" element={<Navigate to={user?'/':'/login'} replace/>}/></Routes></>}</div>;
}
