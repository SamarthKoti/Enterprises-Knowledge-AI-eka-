import {useCallback, useEffect, useRef, useState} from 'react';
import {NavLink, Link, Outlet, useLocation} from 'react-router-dom';
import {Layers3, LogOut, Menu, X, ArrowUpRight} from 'lucide-react';
import {api} from '../services/api';
export default function Workspace({user,onLogout,error}) {
  const links=user.role==='admin'?[['/','Dashboard'],['/documents','Documents'],['/employees','Employees'],['/analytics','Analytics']]:[['/','Dashboard'],['/assistant','AI Assistant'],['/batch','Batch Processing'],['/reports','Reports']];
  const [open,setOpen]=useState(false), [documents,setDocuments]=useState([]), [loading,setLoading]=useState(true), [loadError,setLoadError]=useState('');
  const [messages,setMessages]=useState([]),[asking,setAsking]=useState(false);
  const {pathname}=useLocation();
  const nav=useRef(null);
  const refresh=useCallback(async () => {
    setLoading(true);setLoadError('');
    try {setDocuments(user.role==='admin'?await api('/documents'):[]);} catch(e) {setLoadError(e.message);} finally {setLoading(false);}
  },[user.role]);
  useEffect(()=>{refresh();},[refresh]);
  useEffect(()=>{setOpen(false);},[pathname]);
  useEffect(()=>{
    const update=()=>{
      const active=nav.current?.querySelector('[aria-current="page"]');
      if(active){nav.current.style.setProperty('--nav-x',`${active.offsetLeft}px`);nav.current.style.setProperty('--nav-w',`${active.offsetWidth}px`);}
    };
    update();window.addEventListener('resize',update);return()=>window.removeEventListener('resize',update);
  },[pathname,open]);
  useEffect(()=>{
    const observer=new IntersectionObserver(entries=>{entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('revealed');observer.unobserve(entry.target);}});},{threshold:.08});
    document.querySelectorAll('[data-reveal]').forEach(element=>observer.observe(element));
    return()=>observer.disconnect();
  },[pathname,loading]);
  return <div className="workspace"><a href="#main" className="skip-link">Skip to content</a><header className="app-header"><Link to="/" className="brand" aria-label="Enterprise Knowledge AI home"><Layers3 size={23}/><span>eka<span className="brand-star">✳</span></span><span className="brand-caption">ENTERPRISE<br/>KNOWLEDGE AI</span></Link><nav id="main-nav" ref={nav} className={open?'main-nav is-open':'main-nav'} aria-label="Main navigation"><span className="nav-indicator" aria-hidden="true"/>{links.map(([path,title])=><NavLink end={path==='/'} key={path} to={path}>{title}</NavLink>)}</nav><div className="header-actions"><span className="user-avatar" title={user.email}>{user.email[0].toUpperCase()}</span><button className="icon-button" onClick={onLogout} title="Sign out" aria-label="Sign out"><LogOut size={16}/></button><button className="icon-button mobile-toggle" onClick={()=>setOpen(!open)} aria-expanded={open} aria-controls="main-nav" aria-label={open?'Close navigation':'Open navigation'}>{open?<X size={20}/>:<Menu size={20}/>}</button></div></header>{error&&<p role="alert" className="error global-error">{error}</p>}<main id="main" className="page-content" key={pathname}><Outlet context={{user,documents,loading,loadError,refresh,messages,setMessages,asking,setAsking}}/></main><footer className="workspace-footer"><Link to="/" className="brand"><Layers3 size={20}/> eka</Link><span>{user.company_name} · {user.role.toUpperCase()}</span><a href="#main">Back to the top <ArrowUpRight size={14}/></a></footer></div>;
}
