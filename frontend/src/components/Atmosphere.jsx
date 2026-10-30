import {useEffect, useRef} from 'react';

export function Orb({className = ''}) {
  const ref = useRef(null);
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    let frame;
    const move = (event) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        ref.current?.style.setProperty('--px', `${(event.clientX / window.innerWidth - .5) * 18}px`);
        ref.current?.style.setProperty('--py', `${(event.clientY / window.innerHeight - .5) * 12}px`);
      });
    };
    window.addEventListener('pointermove', move, {passive:true});
    return () => {window.removeEventListener('pointermove', move); cancelAnimationFrame(frame);};
  }, []);
  return <div ref={ref} className={`orb-scene ${className}`} aria-hidden="true"><div className="orb-halo"/><div className="luminous-orb"><div className="orb-silk"/><div className="orb-shadow"/></div><div className="orb-orbit"/></div>;
}

export function Sculpture({variant = 'violet'}) {
  return <div className={`sculpture ${variant}`} aria-hidden="true"><div className="sculpture-ring ring-a"/><div className="sculpture-ring ring-b"/><div className="sculpture-core"/></div>;
}

export default function Atmosphere() {
  return <div className="atmosphere" aria-hidden="true"><div className="ambient"/><div className="grid"/><div className="metal-sphere metal-one"/><div className="metal-sphere metal-two"/><div className="metal-sphere metal-three"/></div>;
}

export function LightRibbons(){
 const paths=['M-200 60 C200 80 340 660 860 420 S1370 120 1700 180','M-200 310 C300 180 520 370 830 470 S1300 760 1700 900','M-180 680 C260 540 460 410 800 430 S1280 350 1680 210'];
 return <div className="ribbon-stage" aria-hidden="true"><svg viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice"><defs><linearGradient id="ribbon-color"><stop stopColor="#3755ff"/><stop offset=".35" stopColor="#651eff"/><stop offset=".58" stopColor="#68eaff"/><stop offset=".72" stopColor="#fc50df"/><stop offset="1" stopColor="#4934ff"/></linearGradient><filter id="ribbon-glow" x="-40%" y="-100%" width="180%" height="300%"><feGaussianBlur stdDeviation="17"/></filter><filter id="ribbon-soft" x="-30%" y="-80%" width="160%" height="260%"><feGaussianBlur stdDeviation="3"/></filter></defs>{paths.map((d,i)=><g className={`ribbon ribbon-${i}`} key={d}><path d={d} stroke="url(#ribbon-color)" strokeWidth="60" filter="url(#ribbon-glow)" opacity=".65"/><path d={d} stroke="#632dff" strokeWidth="22" filter="url(#ribbon-soft)"/><path d={d} stroke="url(#ribbon-color)" strokeWidth="7"/><path d={d} stroke="#e679ff" strokeWidth="2" transform="translate(0,-4)" opacity=".8"/></g>)}</svg></div>;
}
