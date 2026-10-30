import GlassCard from './GlassCard';
export default function GlassFolder({children,label='KNOWLEDGE WORKSPACE',className=''}) {
 return <GlassCard className={`glass-folder ${className}`}><div className="folder-tab">{label}</div><div className="folder-body">{children}</div></GlassCard>;
}
