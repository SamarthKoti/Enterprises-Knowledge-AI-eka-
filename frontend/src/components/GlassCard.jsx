export default function GlassCard({children,className='',label,...props}) {
 return <section className={`glass-card ${className}`} {...props}>{label&&<div className="card-label">{label}</div>}{children}</section>;
}
