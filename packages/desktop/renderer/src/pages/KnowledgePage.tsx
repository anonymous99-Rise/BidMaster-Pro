import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Building2, Plus, Trash2, UploadCloud, FolderArchive, Search, Loader2, Check, X,
  AlertTriangle, Award, Users, Briefcase, Wallet, ShieldCheck, LayoutDashboard,
  FolderOpen, CheckCircle, Database, RefreshCw, RotateCcw, File as FileIcon,
  Share2, ZoomIn, ZoomOut, Maximize2,
} from 'lucide-react';
import {
  kbApi, type KbCompany, type KbCard, type KbReviewItem, type KbCertType,
  type KbExpiryAlert, type KbBuildTaskInfo, type KbFileInfo, type KbCategory,
  type KbGraph, type KbGraphNode,
} from '../services/api';

type KbTab = 'overview' | 'graph' | 'sub-libraries' | 'review' | 'alerts' | 'cert-dict' | 'files';

const SUBS: Array<{ key: KbCategory; label: string; desc: string; icon: typeof Award; color: string }> = [
  { key: 'certificate', label: '资质证书', desc: '企业资质/体系/许可证', icon: Award, color: '#3b82f6' },
  { key: 'personnel', label: '从业资源', desc: '人员/职称/人员证书', icon: Users, color: '#059669' },
  { key: 'achievement', label: '业绩库', desc: '合同/项目/中标', icon: Briefcase, color: '#d97706' },
  { key: 'financial', label: '财务库', desc: '审计报表/财务指标', icon: Wallet, color: '#7c3aed' },
  { key: 'credit', label: '信用库', desc: 'AAA/信用记录', icon: ShieldCheck, color: '#0d9488' },
];

const CATEGORY_LABELS: Record<string, string> = {
  certificate: '资质证书', personnel: '从业资源', achievement: '业绩库',
  financial: '财务库', credit: '信用库',
};

const STATUS_BADGE: Record<string, { text: string; color: string; bg: string }> = {
  valid: { text: '有效', color: '#059669', bg: '#ecfdf5' },
  expiring: { text: '临期', color: '#d97706', bg: '#fffbeb' },
  expired: { text: '已过期', color: '#dc2626', bg: '#fef2f2' },
  needs_completion: { text: '待补全', color: '#6b7280', bg: '#f3f4f6' },
};

const PARSE_STATUS: Record<string, { text: string; color: string }> = {
  pending: { text: '待解析', color: '#94a3b8' },
  parsing: { text: '解析中', color: '#3b82f6' },
  parsed: { text: '已解析', color: '#059669' },
  failed: { text: '失败', color: '#dc2626' },
};

const TASK_STATUS: Record<string, { text: string; color: string }> = {
  pending: { text: '待处理', color: '#94a3b8' },
  queued: { text: '已排队', color: '#3b82f6' },
  running: { text: '构建中', color: '#1a56db' },
  done: { text: '已完成', color: '#059669' },
  failed: { text: '失败', color: '#dc2626' },
};

// ============ 样式 ============
const btnPrimary: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 14px', fontSize: 12,
  border: 'none', borderRadius: 8, cursor: 'pointer', background: '#1a56db', color: '#fff', fontWeight: 600,
};
const btnGhost: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 14px', fontSize: 12,
  border: '1px solid #e2e8f0', borderRadius: 8, cursor: 'pointer', background: '#fff', color: '#475569', fontWeight: 500,
};
const btnSuccess: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 5, padding: '5px 12px', fontSize: 12,
  border: 'none', borderRadius: 7, cursor: 'pointer', background: '#059669', color: '#fff', fontWeight: 600,
};
const btnDanger: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 5, padding: '5px 12px', fontSize: 12,
  border: '1px solid #fecaca', borderRadius: 7, cursor: 'pointer', background: '#fff', color: '#dc2626', fontWeight: 600,
};
const inputStyle: React.CSSProperties = {
  padding: '8px 10px', fontSize: 13, border: '1px solid #e2e8f0', borderRadius: 8,
  outline: 'none', background: '#fff', color: '#0f172a', width: '100%',
};

// ============ 工具 ============
function fmtDate(v: unknown): string {
  if (!v) return '—';
  const s = String(v).slice(0, 10);
  return s && s !== 'None' ? s : '—';
}
function fmtSize(bytes: number): string {
  if (!bytes) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
function fmtAmount(v: unknown): string {
  const n = Number(v || 0);
  if (!n) return '—';
  return `${n.toLocaleString()} 万`;
}
function fmtConf(v: unknown): string {
  const n = Number(v || 0);
  return n > 0 ? `${Math.round(n * 100)}%` : '—';
}
function statusText(raw: unknown): { text: string; color: string; bg: string } {
  const s = String(raw || '').toLowerCase();
  return STATUS_BADGE[s] || { text: raw ? String(raw) : '—', color: '#475569', bg: '#f1f5f9' };
}

// ============ 卡片表格 ============
function CardTable({ cards, total, columns }: {
  cards: KbCard[]; total: number;
  columns: Array<{ key: string; label: string; fmt?: (v: unknown) => string }>;
}) {
  if (cards.length === 0) {
    return <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>暂无卡片</div>;
  }
  return (
    <div style={{ border: '1px solid #e2e8f0', borderRadius: 10, background: '#fff', overflow: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ background: '#f8fafc', color: '#64748b', fontSize: 11 }}>
            {columns.map((c) => (
              <th key={c.key} style={{ textAlign: 'left', padding: '9px 12px', fontWeight: 600, whiteSpace: 'nowrap' }}>{c.label}</th>
            ))}
            <th style={{ textAlign: 'left', padding: '9px 12px' }}>审核</th>
            <th style={{ textAlign: 'left', padding: '9px 12px' }}>置信</th>
          </tr>
        </thead>
        <tbody>
          {cards.map((r) => (
            <tr key={String(r.id)} style={{ borderTop: '1px solid #f1f5f9' }}>
              {columns.map((c) => {
                const raw = (r as Record<string, unknown>)[c.key];
                return (
                  <td key={c.key} style={{ padding: '9px 12px', color: '#334155' }}>
                    {c.key === 'status' && typeof raw === 'string' && STATUS_BADGE[raw] ? (
                      <span style={{ padding: '2px 8px', borderRadius: 6, fontSize: 11, fontWeight: 600, background: STATUS_BADGE[raw].bg, color: STATUS_BADGE[raw].color }}>
                        {STATUS_BADGE[raw].text}
                      </span>
                    ) : (
                      c.fmt ? c.fmt(raw) : (raw ? String(raw) : '—')
                    )}
                  </td>
                );
              })}
              <td style={{ padding: '9px 12px' }}>
                <span style={{ padding: '2px 8px', borderRadius: 6, fontSize: 11, fontWeight: 600, background: r.is_audited ? '#ecfdf5' : '#fffbeb', color: r.is_audited ? '#059669' : '#b45309' }}>
                  {r.is_audited ? '已入池' : '待审核'}
                </span>
              </td>
              <td style={{ padding: '9px 12px', color: '#64748b' }}>{fmtConf(r.confidence)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ padding: '8px 12px', background: '#fafafa', borderTop: '1px solid #f1f5f9', fontSize: 11, color: '#94a3b8' }}>共 {total} 条</div>
    </div>
  );
}

// ============ 概览 ============
function Overview({ company, statCards }: {
  company: KbCompany;
  statCards: Array<{ label: string; value: string; icon: typeof Building2; color: string }>;
}) {
  const keys: Array<[string, string]> = [
    ['short_name', '简称'], ['unified_social_code', '信用代码'], ['legal_person', '法人代表'],
    ['industry_code', '行业代码'], ['region', '注册地'], ['contact', '联系方式'],
    ['created_at', '创建时间'],
  ];
  return (
    <div>
      <div style={{ background: 'linear-gradient(135deg,#1e3a8a,#1a56db)', borderRadius: 14, padding: '20px 24px', color: '#fff', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 44, height: 44, borderRadius: 12, background: 'rgba(255,255,255,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Building2 size={22} />
          </div>
          <div>
            <div style={{ fontSize: 17, fontWeight: 700 }}>{company.name}</div>
            <div style={{ fontSize: 12, opacity: 0.85, marginTop: 2 }}>
              {company.is_default && '默认空间'} · 公司 = 租户 = 知识空间
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, marginBottom: 16 }}>
        {statCards.map((s) => (
          <div key={s.label} style={{ border: '1px solid #e2e8f0', borderRadius: 12, background: '#fff', padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 34, height: 34, borderRadius: 9, background: `${s.color}15`, color: s.color, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <s.icon size={17} />
            </div>
            <div>
              <div style={{ fontSize: 18, fontWeight: 700, color: '#0f172a' }}>{s.value}</div>
              <div style={{ fontSize: 11, color: '#94a3b8' }}>{s.label}</div>
            </div>
          </div>
        ))}
      </div>

      <div style={{ border: '1px solid #e2e8f0', borderRadius: 12, background: '#fff' }}>
        <div style={{ padding: '12px 16px', fontSize: 13, fontWeight: 700, color: '#0f172a', borderBottom: '1px solid #f1f5f9' }}>公司信息</div>
        <div style={{ padding: '14px 16px', display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(220px,1fr))', gap: '10px 24px' }}>
          {keys.map(([k, label]) => (
            <div key={k} style={{ fontSize: 12 }}>
              <span style={{ color: '#94a3b8', marginRight: 8 }}>{label}</span>
              <span style={{ color: '#334155', fontWeight: 500 }}>
                {(company[k as keyof KbCompany] ? String(company[k as keyof KbCompany]) : '—')}
              </span>
            </div>
          ))}
          <div style={{ fontSize: 12, gridColumn: '1 / -1' }}>
            <span style={{ color: '#94a3b8', marginRight: 8 }}>简介</span>
            <span style={{ color: '#334155' }}>{company.description || '—'}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ 图谱视图 ============
const NODE_COLORS: Record<string, string> = {
  certificate: '#3b82f6', personnel: '#059669', achievement: '#d97706',
  financial: '#7c3aed', credit: '#0d9488', personnel_certificate: '#10b981',
};
const GRAPH_GROUPS: KbCategory[] = ['certificate', 'personnel', 'achievement', 'financial', 'credit'];
const groupOf = (t: string): KbCategory | null =>
  t === 'personnel_certificate' ? 'personnel' : (GRAPH_GROUPS.includes(t as KbCategory) ? (t as KbCategory) : null);
const clipLabel = (s: string, n = 9) => (s.length > n ? s.slice(0, n) + '…' : s);

function GraphView({ company, graph, loading, auditOnly, onToggleAudit, onRefresh, onJump }: {
  company: KbCompany; graph: KbGraph; loading: boolean;
  auditOnly: boolean; onToggleAudit: (v: boolean) => void;
  onRefresh: () => void; onJump: (cat: KbCategory, node: KbGraphNode) => void;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 900, h: 560 });
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [selected, setSelected] = useState<KbGraphNode | null>(null);
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null);

  // 数据/公司/勾选变化后清空选中, 避免详情面板残留旧节点
  useEffect(() => { setSelected(null); }, [graph, company.id]);

  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  const positions = useMemo(() => {
    const { w, h } = size;
    const cx = w / 2, cy = h / 2;
    const pos = new Map<string, { x: number; y: number }>();
    pos.set('company', { x: cx, y: cy });
    const present = GRAPH_GROUPS.filter((g) => graph.nodes.some((n) => groupOf(n.type) === g));
    const R = Math.min(w, h) * 0.33;
    present.forEach((g, gi) => {
      const a = -Math.PI / 2 + (gi * 2 * Math.PI) / Math.max(present.length, 1);
      const gx = cx + R * Math.cos(a), gy = cy + R * Math.sin(a);
      const items = graph.nodes.filter((n) => groupOf(n.type) === g);
      const step = 32;
      const y0 = gy - ((items.length - 1) * step) / 2;
      items.forEach((n, i) => pos.set(n.id, { x: gx, y: y0 + i * step }));
    });
    return pos;
  }, [graph.nodes, size]);

  const onDown = (e: React.MouseEvent) => {
    drag.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y };
  };
  const onMove = (e: React.MouseEvent) => {
    if (!drag.current) return;
    setPan({ x: drag.current.px + (e.clientX - drag.current.x), y: drag.current.py + (e.clientY - drag.current.y) });
  };
  const onUp = () => { drag.current = null; };
  const reset = () => { setZoom(1); setPan({ x: 0, y: 0 }); };

  const companyLabel = company.short_name || company.name;
  const present = GRAPH_GROUPS.filter((g) => graph.nodes.some((n) => groupOf(n.type) === g));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a' }}>公司资质全景图谱</div>
          <div style={{ fontSize: 11, color: '#64748b' }}>节点=实体卡片(按子库着色)，连线=关系。点击节点查看详情并直达子库。</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: '#475569', cursor: 'pointer' }}>
            <input type="checkbox" checked={auditOnly} onChange={(e) => onToggleAudit(e.target.checked)} /> 仅已入池
          </label>
          <button style={btnGhost} onClick={onRefresh}><RefreshCw size={14} /> 刷新</button>
        </div>
      </div>

      <div ref={boxRef} style={{ position: 'relative', flex: 1, minHeight: 420, border: '1px solid #e2e8f0', borderRadius: 12, background: '#fbfdff', overflow: 'hidden' }}>
        {loading && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(255,255,255,0.6)', zIndex: 5 }}>
            <Loader2 size={22} color="#94a3b8" style={{ animation: 'spin 1s linear infinite' }} />
          </div>
        )}

        {graph.nodes.length === 0 && !loading && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#94a3b8', gap: 8 }}>
            <Share2 size={34} style={{ opacity: 0.4 }} />
            <div style={{ fontSize: 12 }}>暂无实体卡片，先上传资料构建知识库</div>
          </div>
        )}

        <svg
          width="100%" height="100%"
          style={{ cursor: drag.current ? 'grabbing' : 'grab' }}
          onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}
          onWheel={(e) => setZoom((z) => Math.min(2.5, Math.max(0.4, z + (e.deltaY < 0 ? 0.12 : -0.12))))}
        >
          <defs>
            <marker id="kb-arrow" markerWidth="8" markerHeight="8" refX="8" refY="3" orient="auto">
              <path d="M0,0 L8,3 L0,6 Z" fill="#cbd5e1" />
            </marker>
          </defs>
          <g transform={`translate(${pan.x},${pan.y}) scale(${zoom})`}>
            {/* 边 */}
            {graph.edges.map((e) => {
              const s = positions.get(e.src), d = positions.get(e.dst);
              if (!s || !d) return null;
              const mx = (s.x + d.x) / 2, my = (s.y + d.y) / 2 - 18;
              return (
                <path key={e.id}
                  d={`M${s.x},${s.y} Q${mx},${my} ${d.x},${d.y}`}
                  fill="none" stroke="#cbd5e1" strokeWidth={1.4}
                  strokeDasharray={e.audited ? undefined : '4 3'}
                  markerEnd="url(#kb-arrow)" />
              );
            })}
            {/* 公司→各子库 中心辐射 (连到分簇质心, 避免连线过密) */}
            {present.map((g) => {
              const c = positions.get('company');
              const pts = graph.nodes.filter((n) => groupOf(n.type) === g)
                .map((n) => positions.get(n.id)).filter(Boolean) as Array<{ x: number; y: number }>;
              if (!c || !pts.length) return null;
              const gx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
              const gy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
              return <line key={`sp-${g}`} x1={c.x} y1={c.y} x2={gx} y2={gy}
                stroke="#e2e8f0" strokeWidth={1} />;
            })}
            {/* 公司节点 */}
            {(() => {
              if (graph.nodes.length === 0) return null;
              const c = positions.get('company');
              if (!c) return null;
              return (
                <g>
                  <circle cx={c.x} cy={c.y} r={30} fill="#1a56db" stroke="#fff" strokeWidth={3} />
                  <text x={c.x} y={c.y + 4} textAnchor="middle" fontSize={11} fontWeight={700} fill="#fff">
                    {clipLabel(companyLabel, 6)}
                  </text>
                </g>
              );
            })()}
            {/* 子库分组标签 */}
            {present.map((g) => {
              const items = graph.nodes.filter((n) => groupOf(n.type) === g);
              const p = positions.get(items[0]?.id ?? '');
              if (!p) return null;
              const topY = Math.min(...items.map((n) => positions.get(n.id)?.y ?? p.y));
              return (
                <text key={`gl-${g}`} x={p.x} y={topY - 22} textAnchor="middle" fontSize={11} fontWeight={700} fill={NODE_COLORS[g]}>
                  {CATEGORY_LABELS[g]} ({items.length})
                </text>
              );
            })}
            {/* 卡片节点 */}
            {graph.nodes.map((n) => {
              const p = positions.get(n.id);
              if (!p) return null;
              const color = NODE_COLORS[n.type] || '#64748b';
              const isSel = selected?.id === n.id;
              return (
                <g key={n.id} style={{ cursor: 'pointer' }}
                  onClick={(e) => { e.stopPropagation(); setSelected(n); }}>
                  <circle cx={p.x} cy={p.y} r={isSel ? 12 : 9} fill={color}
                    stroke={isSel ? '#0f172a' : (n.audited ? '#fff' : '#f59e0b')}
                    strokeWidth={isSel ? 2.5 : 1.6}
                    strokeDasharray={n.audited ? undefined : '3 2'} />
                  <text x={p.x} y={p.y + 22} textAnchor="middle" fontSize={10} fill="#475569">
                    {clipLabel(n.label)}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>

        {/* 工具栏 */}
        <div style={{ position: 'absolute', right: 12, bottom: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <button title="放大" style={{ ...btnGhost, padding: 6 }} onClick={() => setZoom((z) => Math.min(2.5, z + 0.15))}><ZoomIn size={15} /></button>
          <button title="缩小" style={{ ...btnGhost, padding: 6 }} onClick={() => setZoom((z) => Math.max(0.4, z - 0.15))}><ZoomOut size={15} /></button>
          <button title="复位" style={{ ...btnGhost, padding: 6 }} onClick={reset}><Maximize2 size={15} /></button>
        </div>

        {/* 图例 */}
        {graph.nodes.length > 0 && (
        <div style={{ position: 'absolute', left: 12, bottom: 12, background: 'rgba(255,255,255,0.92)', border: '1px solid #e2e8f0', borderRadius: 9, padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {present.map((g) => (
            <div key={g} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: '#475569' }}>
              <span style={{ width: 10, height: 10, borderRadius: 5, background: NODE_COLORS[g], display: 'inline-block' }} />
              {CATEGORY_LABELS[g]} · {graph.stats[g] ?? 0}
            </div>
          ))}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: '#94a3b8', marginTop: 2 }}>
            <span style={{ width: 10, height: 10, borderRadius: 5, border: '1.5px dashed #f59e0b', display: 'inline-block' }} /> 待审核
          </div>
        </div>
        )}

        {/* 节点详情 */}
        {selected && (
          <div style={{ position: 'absolute', top: 12, right: 12, width: 240, background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, boxShadow: '0 8px 24px rgba(15,23,42,0.12)', overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '9px 12px', borderBottom: '1px solid #f1f5f9' }}>
              <span style={{ width: 10, height: 10, borderRadius: 5, background: NODE_COLORS[selected.type] || '#64748b' }} />
              <span style={{ fontSize: 11, fontWeight: 600, color: '#334155' }}>
                {CATEGORY_LABELS[groupOf(selected.type) || ''] || (selected.type === 'personnel_certificate' ? '人员证书' : selected.type)}
              </span>
              <button onClick={() => setSelected(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8' }}><X size={14} /></button>
            </div>
            <div style={{ padding: '10px 12px' }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a', lineHeight: 1.4 }}>{selected.label}</div>
              {selected.sub && <div style={{ fontSize: 11, color: '#64748b', marginTop: 3 }}>{selected.sub}</div>}
              <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 5, fontWeight: 600, background: selected.audited ? '#ecfdf5' : '#fffbeb', color: selected.audited ? '#059669' : '#b45309' }}>
                  {selected.audited ? '已入池' : '待审核'}
                </span>
                {selected.status && STATUS_BADGE[selected.status] && (
                  <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 5, fontWeight: 600, background: STATUS_BADGE[selected.status].bg, color: STATUS_BADGE[selected.status].color }}>
                    {STATUS_BADGE[selected.status].text}
                  </span>
                )}
              </div>
              {groupOf(selected.type) && (
                <button style={{ ...btnPrimary, width: '100%', justifyContent: 'center', marginTop: 10 }}
                  onClick={() => onJump(groupOf(selected.type) as KbCategory, selected)}>
                  <FolderOpen size={13} /> 在子库中查看
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ============ 主页面 ============
export default function KnowledgePage() {
  const [companies, setCompanies] = useState<KbCompany[]>([]);
  const [activeCompany, setActiveCompany] = useState<KbCompany | null>(null);
  const [tab, setTab] = useState<KbTab>('overview');
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const [showCompany, setShowCompany] = useState(false);
  const [nc, setNc] = useState({ name: '', short_name: '', unified_social_code: '', legal_person: '', industry_code: '', region: '', contact: '', description: '' });

  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);

  const [subKey, setSubKey] = useState<KbCategory>('certificate');
  const [cards, setCards] = useState<KbCard[]>([]);
  const [cardsTotal, setCardsTotal] = useState(0);
  const [cardsFilter, setCardsFilter] = useState({ audit: 'all', status: '', q: '' });
  const [cardsLoading, setCardsLoading] = useState(false);

  const [reviewItems, setReviewItems] = useState<KbReviewItem[]>([]);
  const [alerts, setAlerts] = useState<KbExpiryAlert[]>([]);
  const [graph, setGraph] = useState<KbGraph>({ nodes: [], edges: [], stats: {} });
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphAudit, setGraphAudit] = useState(false);
  const [certTypes, setCertTypes] = useState<KbCertType[]>([]);
  const [tasks, setTasks] = useState<KbBuildTaskInfo[]>([]);
  const [files, setFiles] = useState<KbFileInfo[]>([]);
  const [filesTab, setFilesTab] = useState<'files' | 'tasks'>('files');

  const [showCert, setShowCert] = useState(false);
  const [nct, setNct] = useState({ code: '', name: '', category: 'enterprise', default_valid_months: 0, scope_hint: '' });

  const cid = activeCompany?.id;

  const notify = useCallback((type: 'success' | 'error', text: string) => {
    setToast({ type, text });
    setTimeout(() => setToast(null), 3200);
  }, []);
  const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e));

  const loadCompanies = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await kbApi.listCompanies();
      setCompanies(data.companies);
      setActiveCompany((prev) => (prev && data.companies.some((c) => c.id === prev.id) ? prev : data.companies[0] ?? null));
    } catch (e) {
      notify('error', `加载公司失败: ${errMsg(e)}`);
    } finally {
      setLoading(false);
    }
  }, [notify]);

  const loadCards = useCallback(async (companyId?: string, silent = false) => {
    const id = companyId ?? activeCompany?.id;
    if (!id) return;
    if (!silent) setCardsLoading(true);
    try {
      const { data } = await kbApi.listCards(id, {
        category: subKey,
        audit: cardsFilter.audit as 'all' | 'unaudited' | 'audited',
        status: cardsFilter.status || undefined,
        q: cardsFilter.q || undefined,
        limit: 300,
      });
      setCards(data.cards);
      setCardsTotal(data.total);
    } catch (e) {
      notify('error', `加载卡片失败: ${errMsg(e)}`);
    } finally {
      if (!silent) setCardsLoading(false);
    }
  }, [subKey, cardsFilter, notify]);

  const loadReview = useCallback(async (companyId?: string) => {
    try {
      const { data } = await kbApi.reviewQueue(companyId);
      setReviewItems(data.items);
    } catch (e) { notify('error', `加载人审队列失败: ${errMsg(e)}`); }
  }, [notify]);

  const loadAlerts = useCallback(async (companyId?: string) => {
    try {
      const { data } = await kbApi.expiryAlerts(companyId, 90);
      setAlerts(data.alerts);
    } catch (e) { notify('error', `加载到期提醒失败: ${errMsg(e)}`); }
  }, [notify]);

  const loadCertTypes = useCallback(async () => {
    try {
      const { data } = await kbApi.listCertTypes();
      setCertTypes(data.cert_types);
    } catch (e) { notify('error', `加载证书字典失败: ${errMsg(e)}`); }
  }, [notify]);

  const loadTasks = useCallback(async (companyId?: string) => {
    try {
      const { data } = await kbApi.listBuildTasks(companyId);
      setTasks(data.tasks);
    } catch (e) { notify('error', `加载构建任务失败: ${errMsg(e)}`); }
  }, [notify]);

  const loadFiles = useCallback(async (companyId?: string) => {
    const id = companyId ?? activeCompany?.id;
    if (!id) return;
    try {
      const { data } = await kbApi.listFiles(id);
      setFiles(data.files);
    } catch (e) { notify('error', `加载文件失败: ${errMsg(e)}`); }
  }, [activeCompany, notify]);

  const loadGraph = useCallback(async (companyId?: string, audit = graphAudit, silent = false) => {
    const id = companyId ?? activeCompany?.id;
    if (!id) return;
    if (!silent) setGraphLoading(true);
    try {
      const { data } = await kbApi.graph(id, audit ? 'audited' : 'all');
      setGraph(data);
    } catch (e) { notify('error', `加载图谱失败: ${errMsg(e)}`); }
    finally { if (!silent) setGraphLoading(false); }
  }, [activeCompany, graphAudit, notify]);

  useEffect(() => { loadCompanies(); }, [loadCompanies]);
  // 卡片: 公司/子库/审核状态/证书状态 变更自动重载; 搜索 q 由 Enter 手动触发
  useEffect(() => { if (cid) loadCards(cid); }, [cid, subKey, cardsFilter.audit, cardsFilter.status]);
  useEffect(() => {
    if (!cid) return;
    loadReview(cid); loadAlerts(cid); loadFiles(cid); loadTasks(cid);
  }, [cid, loadReview, loadAlerts, loadFiles, loadTasks]);
  useEffect(() => { if (tab === 'cert-dict') loadCertTypes(); }, [tab, loadCertTypes]);
  useEffect(() => { if (cid && tab === 'graph') loadGraph(cid); }, [cid, tab, graphAudit, loadGraph]);

  // 图谱节点直达子库: 切到子库页签并按标签搜索定位该卡片
  const jumpToSub = async (cat: KbCategory, node: KbGraphNode) => {
    // 人员证书是人员子库下的叶子, 其标签不在人员卡片可搜字段中, 故只定位到子库不搜索
    const q = node.type === 'personnel_certificate' ? '' : node.label;
    setSubKey(cat);
    setCardsFilter({ audit: 'all', status: '', q });
    setTab('sub-libraries');
    if (!cid) return;
    setCardsLoading(true);
    try {
      const { data } = await kbApi.listCards(cid, { category: cat, audit: 'all', q: q || undefined, limit: 300 });
      setCards(data.cards);
      setCardsTotal(data.total);
    } catch (e) { notify('error', errMsg(e)); }
    finally { setCardsLoading(false); }
  };

  const createCompany = async () => {
    if (!nc.name.trim()) { notify('error', '公司名称必填'); return; }
    try {
      const { data } = await kbApi.createCompany(nc);
      setCompanies((p) => [data, ...p]);
      setActiveCompany(data);
      setShowCompany(false);
      setNc({ name: '', short_name: '', unified_social_code: '', legal_person: '', industry_code: '', region: '', contact: '', description: '' });
      notify('success', '公司空间已创建');
    } catch (e) { notify('error', errMsg(e)); }
  };

  const deleteCompany = async (c: KbCompany) => {
    if (!window.confirm(`删除公司空间「${c.name}」及其全部知识数据?`)) return;
    try {
      await kbApi.deleteCompany(c.id);
      const rest = companies.filter((x) => x.id !== c.id);
      setCompanies(rest);
      setActiveCompany(rest[0] ?? null);
      notify('success', '已删除');
    } catch (e) { notify('error', errMsg(e)); }
  };

  const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || !cid) return;
    setUploading(true);
    try {
      await kbApi.uploadFile(cid, file, true);
      notify('success', `已上传 ${file.name}，构建任务启动`);
      loadFiles(cid); loadTasks(cid);
    } catch (e) { notify('error', `上传失败: ${errMsg(e)}`); }
    finally { setUploading(false); }
  };

  const onUploadFolder = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || !cid) return;
    setUploading(true);
    try {
      await kbApi.uploadFolder(cid, file, true);
      notify('success', '整包已上传，构建任务已启动');
      loadFiles(cid); loadTasks(cid);
    } catch (e) { notify('error', `整包上传失败: ${errMsg(e)}`); }
    finally { setUploading(false); }
  };

  const onReview = async (item: KbReviewItem, ok: boolean) => {
    try {
      if (ok) await kbApi.approveCard(item.entity_type, item.id);
      else await kbApi.rejectCard(item.entity_type, item.id);
      notify('success', ok ? '已通过并入池' : '已拒绝');
      setReviewItems((p) => p.filter((i) => i.id !== item.id));
      if (cid && item.entity_type === subKey) loadCards(cid, true);
    } catch (e) { notify('error', errMsg(e)); }
  };

  const createCert = async () => {
    if (!nct.code.trim() || !nct.name.trim()) { notify('error', 'code 与名称必填'); return; }
    try {
      await kbApi.createCertType(nct);
      notify('success', '证书类型已添加');
      setShowCert(false);
      setNct({ code: '', name: '', category: 'enterprise', default_valid_months: 0, scope_hint: '' });
      loadCertTypes();
    } catch (e) { notify('error', errMsg(e)); }
  };

  const deleteCert = async (ct: KbCertType) => {
    if (ct.is_builtin) { notify('error', '内置证书类型不可删除'); return; }
    if (!window.confirm(`删除证书类型「${ct.name}」?`)) return;
    try {
      await kbApi.deleteCertType(ct.id);
      notify('success', '已删除');
      loadCertTypes();
    } catch (e) { notify('error', errMsg(e)); }
  };

  const retryTask = async (id: string) => {
    try {
      await kbApi.retryBuildTask(id);
      notify('success', '已重新投递构建任务');
      loadTasks(cid);
    } catch (e) { notify('error', errMsg(e)); }
  };

  // 概览统计卡: 当前公司维度 (队列保持全局, 文件按当前公司)
  const statCards = [
    { label: '公司空间', value: String(companies.length), icon: Building2, color: '#3b82f6' },
    { label: '来源文件', value: String(files.length), icon: FolderOpen, color: '#475569' },
    { label: '待审核卡片', value: String(reviewItems.length), icon: CheckCircle, color: '#d97706' },
    { label: '临期/过期', value: String(alerts.length), icon: AlertTriangle, color: '#dc2626' },
  ];

  const CARD_COLUMNS: Record<KbCategory, Array<{ key: string; label: string; fmt?: (v: unknown) => string }>> = {
    certificate: [
      { key: 'name', label: '证书名称' },
      { key: 'number', label: '编号' },
      { key: 'level', label: '等级' },
      { key: 'expiry_date', label: '有效期至', fmt: fmtDate },
      { key: 'status', label: '状态' },
    ],
    personnel: [
      { key: 'name', label: '姓名' },
      { key: 'title', label: '职称' },
      { key: 'role', label: '拟派岗位' },
      { key: 'gender', label: '性别' },
    ],
    achievement: [
      { key: 'project_name', label: '项目名称' },
      { key: 'client_name', label: '业主' },
      { key: 'sign_date', label: '签订日期', fmt: fmtDate },
      { key: 'contract_amount', label: '金额(万)', fmt: fmtAmount },
      { key: 'year', label: '年份' },
    ],
    financial: [
      { key: 'report_type', label: '报表类型' },
      { key: 'year', label: '年份' },
      { key: 'total_assets', label: '总资产(万)', fmt: fmtAmount },
      { key: 'revenue', label: '营收(万)', fmt: fmtAmount },
      { key: 'net_profit', label: '净利润(万)', fmt: fmtAmount },
      { key: 'debt_ratio', label: '负债率%' },
    ],
    credit: [
      { key: 'title', label: '名称' },
      { key: 'credit_type', label: '类型' },
      { key: 'check_date', label: '日期', fmt: fmtDate },
      { key: 'result', label: '结果' },
    ],
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#f8fafc' }}>
      {/* ===== 顶栏 ===== */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 24px', borderBottom: '1px solid #e2e8f0', background: '#fff' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Building2 size={20} color="#1a56db" />
          <h2 style={{ fontSize: 16, fontWeight: 700, color: '#0f172a', margin: 0 }}>知识库</h2>
          <span style={{ fontSize: 11, color: '#94a3b8' }}>公司空间 · 子库 · 人审入池 · 到期提醒</span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button style={btnPrimary} onClick={() => setShowCompany(true)} disabled={uploading}>
            <Plus size={15} /> 新建公司
          </button>
          <button style={btnGhost} onClick={() => fileRef.current?.click()} disabled={!cid || uploading}>
            {uploading ? <Loader2 size={15} style={{ animation: 'spin 1s linear infinite' }} /> : <UploadCloud size={15} />} 上传文件
          </button>
          <button style={btnGhost} onClick={() => folderRef.current?.click()} disabled={!cid || uploading}>
            <FolderArchive size={15} /> 整包(ZIP)
          </button>
          <input ref={fileRef} type="file" style={{ display: 'none' }} onChange={onUpload} />
          <input ref={folderRef} type="file" accept=".zip,application/zip" style={{ display: 'none' }} onChange={onUploadFolder} />
        </div>
      </div>

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        {/* ===== 左栏: 公司树 ===== */}
        <div style={{ width: 248, borderRight: '1px solid #e2e8f0', background: '#fff', overflowY: 'auto', padding: '12px 8px', flexShrink: 0 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.08em', padding: '0 10px 8px' }}>公司空间</div>
          {companies.length === 0 && !loading && (
            <div style={{ textAlign: 'center', padding: '28px 12px', color: '#94a3b8', fontSize: 12, lineHeight: 1.6 }}>
              还没有公司空间
              <br />点击「新建公司」开始
            </div>
          )}
          {companies.map((c) => (
            <div
              key={c.id}
              onClick={() => setActiveCompany(c)}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', borderRadius: 8,
                cursor: 'pointer', marginBottom: 2,
                background: cid === c.id ? '#eff6ff' : 'transparent',
                border: cid === c.id ? '1px solid #bfdbfe' : '1px solid transparent',
              }}
            >
              {c.is_default ? <ShieldCheck size={15} color="#1a56db" /> : <Building2 size={15} color="#64748b" />}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: cid === c.id ? '#1a56db' : '#334155', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.name}</div>
                <div style={{ fontSize: 10, color: '#94a3b8', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.region || c.short_name || (c.is_default ? '默认空间' : '—')}</div>
              </div>
              {!c.is_default && (
                <button
                  title="删除公司空间"
                  onClick={(e) => { e.stopPropagation(); deleteCompany(c); }}
                  style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#cbd5e1', padding: 2 }}
                ><Trash2 size={13} /></button>
              )}
            </div>
          ))}
        </div>

        {/* ===== 右区 ===== */}
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', gap: 2, padding: '0 20px', borderBottom: '1px solid #e2e8f0', background: '#fff', overflowX: 'auto' }}>
            {([
              { key: 'overview', label: '概览', icon: LayoutDashboard },
              { key: 'graph', label: '图谱', icon: Share2 },
              { key: 'sub-libraries', label: '子库', icon: FolderOpen },
              { key: 'review', label: '人审队列', icon: CheckCircle, badge: reviewItems.length },
              { key: 'alerts', label: '到期提醒', icon: AlertTriangle, badge: alerts.length },
              { key: 'files', label: '文件与任务', icon: Database },
              { key: 'cert-dict', label: '证书字典', icon: ShieldCheck },
            ] as Array<{ key: KbTab; label: string; icon: typeof LayoutDashboard; badge?: number }>).map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6, padding: '10px 13px', fontSize: 12,
                  background: 'transparent', border: 'none', cursor: 'pointer', whiteSpace: 'nowrap',
                  color: tab === t.key ? '#1a56db' : '#64748b', fontWeight: tab === t.key ? 600 : 500,
                  borderBottom: tab === t.key ? '2px solid #1a56db' : '2px solid transparent',
                }}
              >
                <t.icon size={15} /> {t.label}
                {t.badge != null && t.badge > 0 && (
                  <span style={{ background: '#dc2626', color: '#fff', borderRadius: 7, padding: '0 5px', fontSize: 10, lineHeight: '14px' }}>{t.badge}</span>
                )}
              </button>
            ))}
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: '18px 22px' }}>
            {!cid && !loading && (
              <div style={{ textAlign: 'center', padding: '60px 0', color: '#94a3b8' }}>
                <Building2 size={36} style={{ marginBottom: 12, opacity: 0.4 }} />
                <div>请先创建公司空间</div>
              </div>
            )}

            {cid && tab === 'overview' && <Overview company={activeCompany!} statCards={statCards} />}

            {cid && tab === 'graph' && (
              <GraphView
                company={activeCompany!}
                graph={graph}
                loading={graphLoading}
                auditOnly={graphAudit}
                onToggleAudit={setGraphAudit}
                onRefresh={() => loadGraph(cid)}
                onJump={jumpToSub}
              />
            )}

            {cid && tab === 'sub-libraries' && (
              <div>
                <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
                  {SUBS.map((s) => (
                    <button
                      key={s.key}
                      onClick={() => setSubKey(s.key)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 7,
                        padding: '8px 14px', borderRadius: 9, cursor: 'pointer',
                        border: subKey === s.key ? `1.5px solid ${s.color}` : '1px solid #e2e8f0',
                        background: subKey === s.key ? `${s.color}12` : '#fff',
                        color: subKey === s.key ? s.color : '#475569',
                        fontSize: 12, fontWeight: 600,
                      }}
                    >
                      <s.icon size={14} /> {s.label}
                      <span style={{ fontSize: 10, fontWeight: 400 }}>{s.desc}</span>
                    </button>
                  ))}
                </div>

                <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, border: '1px solid #e2e8f0', borderRadius: 8, padding: '6px 10px', background: '#fff', width: 220 }}>
                    <Search size={14} color="#94a3b8" />
                    <input
                      value={cardsFilter.q}
                      placeholder="搜索名称/编号…"
                      onChange={(e) => setCardsFilter({ ...cardsFilter, q: e.target.value })}
                      onKeyDown={(e) => { if (e.key === 'Enter') loadCards(); }}
                      style={{ border: 'none', outline: 'none', flex: 1, fontSize: 12, background: 'transparent' }}
                    />
                  </div>
                  <select
                    value={cardsFilter.audit}
                    onChange={(e) => setCardsFilter({ ...cardsFilter, audit: e.target.value })}
                    style={{ ...inputStyle, width: 'auto' }}
                  >
                    <option value="all">全部审核状态</option>
                    <option value="unaudited">待审核</option>
                    <option value="audited">已入池</option>
                  </select>
                  {subKey === 'certificate' && (
                    <select
                      value={cardsFilter.status}
                      onChange={(e) => setCardsFilter({ ...cardsFilter, status: e.target.value })}
                      style={{ ...inputStyle, width: 'auto' }}
                    >
                      <option value="">全部状态</option>
                      <option value="valid">有效</option>
                      <option value="expiring">临期</option>
                      <option value="expired">已过期</option>
                      <option value="needs_completion">待补全</option>
                    </select>
                  )}
                  <button style={btnGhost} onClick={() => loadCards()}><RefreshCw size={14} /> 刷新</button>
                </div>

                {cardsLoading ? (
                  <div style={{ textAlign: 'center', padding: 30 }}><Loader2 size={20} color="#94a3b8" style={{ animation: 'spin 1s linear infinite' }} /></div>
                ) : (
                  <CardTable cards={cards} total={cardsTotal} columns={CARD_COLUMNS[subKey]} />
                )}
              </div>
            )}

            {tab === 'review' && (
              <div>
                <div style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a' }}>人审队列</div>
                  <div style={{ fontSize: 11, color: '#64748b' }}>AI 从源文件抽取的卡片，人工确认后才可进入自动勾对池；拒绝即删除。</div>
                </div>
                {reviewItems.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: 30, color: '#94a3b8' }}>暂无待审核卡片</div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {reviewItems.map((it) => {
                      const f = it.fields as Record<string, unknown>;
                      const title = String(f.name || f.project_name || f.title || '(未命名卡片)');
                      return (
                        <div key={it.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '11px 14px', border: '1px solid #e2e8f0', borderRadius: 10, background: '#fff' }}>
                          <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 6, background: '#eff6ff', color: '#1a56db', fontWeight: 600, whiteSpace: 'nowrap' }}>
                            {CATEGORY_LABELS[it.entity_type] || it.entity_type}
                          </span>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 13, fontWeight: 600, color: '#0f172a' }}>{title}</div>
                            <div style={{ fontSize: 11, color: '#94a3b8' }}>
                              {Object.entries(f).filter(([, v]) => v && typeof v !== 'object').slice(0, 5).map(([k, v]) => `${k}: ${String(v)}`).join(' · ') || '—'}
                            </div>
                          </div>
                          <button style={btnSuccess} onClick={() => onReview(it, true)}><Check size={14} /> 通过</button>
                          <button style={btnDanger} onClick={() => onReview(it, false)}><X size={14} /> 拒绝</button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {tab === 'alerts' && (
              <div>
                <div style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a' }}>到期提醒</div>
                  <div style={{ fontSize: 11, color: '#64748b' }}>已入池证书/人员证书有效期 ≤90 天或已过期。</div>
                </div>
                {alerts.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: 30, color: '#94a3b8' }}>暂无到期预警</div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {alerts.map((a) => {
                      const badge = statusText(a.status);
                      return (
                        <div key={a.id} style={{ padding: '12px 14px', border: '1px solid #e2e8f0', borderRadius: 10, background: '#fff', display: 'flex', alignItems: 'center', gap: 10 }}>
                          <AlertTriangle size={16} color={badge.color} />
                          <div style={{ flex: 1 }}>
                            <div style={{ fontSize: 13, fontWeight: 600, color: '#0f172a' }}>{a.name || '未命名'}</div>
                            <div style={{ fontSize: 11, color: '#94a3b8' }}>{CATEGORY_LABELS[a.entity_type] || a.entity_type} · {fmtDate(a.expiry_date)}</div>
                          </div>
                          <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 6, fontWeight: 700, background: badge.bg, color: badge.color }}>
                            {a.days_left < 0 ? `已过期 ${-a.days_left} 天` : a.days_left <= 0 ? '今天到期' : `${a.days_left} 天`}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {tab === 'cert-dict' && (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a' }}>证书类型字典</div>
                    <div style={{ fontSize: 11, color: '#64748b' }}>可配置的证书分类，用于资质自检与团队优化器。</div>
                  </div>
                  <button style={btnPrimary} onClick={() => setShowCert(true)}><Plus size={14} /> 新增类型</button>
                </div>
                <div style={{ border: '1px solid #e2e8f0', borderRadius: 10, background: '#fff', overflow: 'hidden' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                    <thead>
                      <tr style={{ background: '#f8fafc', color: '#64748b', fontSize: 11 }}>
                        <th style={{ textAlign: 'left', padding: '9px 12px' }}>名称</th>
                        <th style={{ textAlign: 'left', padding: '9px 12px' }}>code</th>
                        <th style={{ textAlign: 'left', padding: '9px 12px' }}>类别</th>
                        <th style={{ textAlign: 'left', padding: '9px 12px' }}>典型有效期(月)</th>
                        <th style={{ textAlign: 'left', padding: '9px 12px' }}>范围提示</th>
                        <th style={{ textAlign: 'left', padding: '9px 12px' }}>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {certTypes.map((ct) => (
                        <tr key={ct.id} style={{ borderTop: '1px solid #f1f5f9' }}>
                          <td style={{ padding: '9px 12px', fontWeight: 600, color: '#0f172a' }}>{ct.name}</td>
                          <td style={{ padding: '9px 12px', color: '#475569' }}>{ct.code}</td>
                          <td style={{ padding: '9px 12px', color: '#475569' }}>{CATEGORY_LABELS[ct.category] || ct.category}</td>
                          <td style={{ padding: '9px 12px', color: '#475569' }}>{ct.default_valid_months || '—'}</td>
                          <td style={{ padding: '9px 12px', color: '#94a3b8' }}>{ct.scope_hint || '—'}</td>
                          <td style={{ padding: '9px 12px' }}>
                            {ct.is_builtin ? <span style={{ fontSize: 11, color: '#94a3b8' }}>内置</span> : (
                              <button onClick={() => deleteCert(ct)} style={{ ...btnGhost, padding: '4px 8px' }} title="删除"><Trash2 size={13} color="#dc2626" /></button>
                            )}
                          </td>
                        </tr>
                      ))}
                      {certTypes.length === 0 && (
                        <tr><td colSpan={6} style={{ padding: 24, textAlign: 'center', color: '#94a3b8' }}>暂无证书类型</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {tab === 'files' && (
              <div>
                <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                  {(['files', 'tasks'] as const).map((t) => (
                    <button key={t} onClick={() => setFilesTab(t)} style={{
                      padding: '6px 12px', fontSize: 12, borderRadius: 7, cursor: 'pointer',
                      border: filesTab === t ? '1px solid #1a56db' : '1px solid #e2e8f0',
                      background: filesTab === t ? '#eff6ff' : '#fff',
                      color: filesTab === t ? '#1a56db' : '#64748b', fontWeight: 600,
                    }}>
                      {t === 'files' ? `来源文件 (${files.length})` : `构建任务 (${tasks.length})`}
                    </button>
                  ))}
                </div>

                {!cid ? (
                  <div style={{ textAlign: 'center', padding: 30, color: '#94a3b8' }}>请选择公司空间</div>
                ) : filesTab === 'files' ? (
                  <div style={{ border: '1px solid #e2e8f0', borderRadius: 10, background: '#fff', overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                      <thead>
                        <tr style={{ background: '#f8fafc', color: '#64748b', fontSize: 11 }}>
                          <th style={{ textAlign: 'left', padding: '9px 12px' }}>文件</th>
                          <th style={{ textAlign: 'left', padding: '9px 12px' }}>子库</th>
                          <th style={{ textAlign: 'left', padding: '9px 12px' }}>解析</th>
                          <th style={{ textAlign: 'left', padding: '9px 12px' }}>方式</th>
                          <th style={{ textAlign: 'left', padding: '9px 12px' }}>大小</th>
                          <th style={{ textAlign: 'left', padding: '9px 12px' }}>状态</th>
                        </tr>
                      </thead>
                      <tbody>
                        {files.map((f) => {
                          const ps = PARSE_STATUS[f.parse_status] || { text: f.parse_status, color: '#94a3b8' };
                          return (
                            <tr key={f.id} style={{ borderTop: '1px solid #f1f5f9' }}>
                              <td style={{ padding: '9px 12px', color: '#334155', maxWidth: 280 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6, overflow: 'hidden' }}>
                                  <FileIcon size={13} color="#94a3b8" style={{ flexShrink: 0 }} />
                                  <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{f.filename}</span>
                                </div>
                                {f.rel_dir && <div style={{ fontSize: 10, color: '#cbd5e1' }}>{f.rel_dir}</div>}
                              </td>
                              <td style={{ padding: '9px 12px' }}>{CATEGORY_LABELS[f.category] || f.category || '—'}</td>
                              <td style={{ padding: '9px 12px' }}><span style={{ color: ps.color }}>{ps.text}</span></td>
                              <td style={{ padding: '9px 12px', color: '#64748b' }}>{f.parse_method || '—'}</td>
                              <td style={{ padding: '9px 12px', color: '#64748b' }}>{fmtSize(f.file_size)}</td>
                              <td style={{ padding: '9px 12px', color: '#94a3b8' }}>{f.error ? '—' : '正常'}</td>
                            </tr>
                          );
                        })}
                        {files.length === 0 && (
                          <tr><td colSpan={6} style={{ padding: 24, textAlign: 'center', color: '#94a3b8' }}>暂无来源文件</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div style={{ border: '1px solid #e2e8f0', borderRadius: 10, background: '#fff', overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                      <thead>
                        <tr style={{ background: '#f8fafc', color: '#64748b', fontSize: 11 }}>
                          <th style={{ textAlign: 'left', padding: '9px 12px' }}>任务</th>
                          <th style={{ textAlign: 'left', padding: '9px 12px' }}>状态</th>
                          <th style={{ textAlign: 'left', padding: '9px 12px' }}>进度</th>
                          <th style={{ textAlign: 'left', padding: '9px 12px' }}>实体</th>
                          <th style={{ textAlign: 'left', padding: '9px 12px' }}>关系</th>
                          <th style={{ textAlign: 'left', padding: '9px 12px' }}>操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {tasks.map((t) => {
                          const st = TASK_STATUS[t.status] || { text: t.status, color: '#94a3b8' };
                          return (
                            <tr key={t.id} style={{ borderTop: '1px solid #f1f5f9' }}>
                              <td style={{ padding: '9px 12px', color: '#334155' }}>{t.id.slice(0, 8)}…<div style={{ fontSize: 10, color: '#cbd5e1' }}>{fmtDate(t.created_at)}</div></td>
                              <td style={{ padding: '9px 12px' }}><span style={{ color: st.color, fontWeight: 600 }}>{st.text}</span></td>
                              <td style={{ padding: '9px 12px', color: '#64748b' }}>{t.processed_files}/{t.total_files}</td>
                              <td style={{ padding: '9px 12px', color: '#64748b' }}>{t.created_entities}</td>
                              <td style={{ padding: '9px 12px', color: '#64748b' }}>{t.created_edges}</td>
                              <td style={{ padding: '9px 12px' }}>
                                {t.status === 'failed' && <button style={btnGhost} onClick={() => retryTask(t.id)}><RotateCcw size={13} /> 重试</button>}
                                {t.error && <div style={{ fontSize: 10, color: '#dc2626', marginTop: 4 }}>{t.error.slice(0, 60)}</div>}
                              </td>
                            </tr>
                          );
                        })}
                        {tasks.length === 0 && (
                          <tr><td colSpan={6} style={{ padding: 24, textAlign: 'center', color: '#94a3b8' }}>暂无构建任务</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ===== 新建公司弹窗 ===== */}
      {showCompany && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 2000, padding: 20 }}>
          <div style={{ background: '#fff', borderRadius: 14, width: 440, maxWidth: '100%', boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid #f1f5f9', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>新建公司空间</div>
              <button onClick={() => setShowCompany(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8' }}><X size={18} /></button>
            </div>
            <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              <input style={inputStyle} placeholder="公司名称 (必填)" value={nc.name} onChange={(e) => setNc({ ...nc, name: e.target.value })} />
              <div style={{ display: 'flex', gap: 10 }}>
                <input style={inputStyle} placeholder="简称" value={nc.short_name} onChange={(e) => setNc({ ...nc, short_name: e.target.value })} />
                <input style={inputStyle} placeholder="统一社会信用代码" value={nc.unified_social_code} onChange={(e) => setNc({ ...nc, unified_social_code: e.target.value })} />
              </div>
              <div style={{ display: 'flex', gap: 10 }}>
                <input style={inputStyle} placeholder="法定代表人" value={nc.legal_person} onChange={(e) => setNc({ ...nc, legal_person: e.target.value })} />
                <input style={inputStyle} placeholder="行业代码 (如 12)" value={nc.industry_code} onChange={(e) => setNc({ ...nc, industry_code: e.target.value })} />
              </div>
              <div style={{ display: 'flex', gap: 10 }}>
                <input style={inputStyle} placeholder="注册地" value={nc.region} onChange={(e) => setNc({ ...nc, region: e.target.value })} />
                <input style={inputStyle} placeholder="联系方式" value={nc.contact} onChange={(e) => setNc({ ...nc, contact: e.target.value })} />
              </div>
              <textarea style={{ ...inputStyle, minHeight: 60, resize: 'vertical' }} placeholder="简介" value={nc.description} onChange={(e) => setNc({ ...nc, description: e.target.value })} />
              <button style={{ ...btnPrimary, justifyContent: 'center', padding: '10px', fontSize: 13 }} onClick={createCompany}>创建</button>
            </div>
          </div>
        </div>
      )}

      {/* ===== 新增证书类型弹窗 ===== */}
      {showCert && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 2000, padding: 20 }}>
          <div style={{ background: '#fff', borderRadius: 14, width: 400, maxWidth: '100%', boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid #f1f5f9', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>新增证书类型</div>
              <button onClick={() => setShowCert(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8' }}><X size={18} /></button>
            </div>
            <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              <input style={inputStyle} placeholder="code (如 iso9001)" value={nct.code} onChange={(e) => setNct({ ...nct, code: e.target.value })} />
              <input style={inputStyle} placeholder="名称" value={nct.name} onChange={(e) => setNct({ ...nct, name: e.target.value })} />
              <select style={inputStyle} value={nct.category} onChange={(e) => setNct({ ...nct, category: e.target.value })}>
                <option value="enterprise">企业资质</option>
                <option value="personnel">人员</option>
                <option value="financial">财务</option>
              </select>
              <input style={inputStyle} type="number" placeholder="典型有效期(月)，0=长期" value={nct.default_valid_months || ''} onChange={(e) => setNct({ ...nct, default_valid_months: Number(e.target.value) })} />
              <input style={inputStyle} placeholder="范围提示(可选)" value={nct.scope_hint} onChange={(e) => setNct({ ...nct, scope_hint: e.target.value })} />
              <button style={{ ...btnPrimary, justifyContent: 'center', padding: '10px', width: '100%' }} onClick={createCert}>保存</button>
            </div>
          </div>
        </div>
      )}

      {/* ===== Toast ===== */}
      {toast && (
        <div style={{
          position: 'fixed', top: 24, right: 24, zIndex: 9999,
          padding: '10px 16px', borderRadius: 8, fontSize: 13,
          background: toast.type === 'success' ? '#059669' : '#dc2626', color: '#fff',
          boxShadow: '0 4px 16px rgba(0,0,0,0.18)', display: 'flex', alignItems: 'center', gap: 8,
        }}>
          {toast.type === 'success' ? <Check size={15} /> : <AlertTriangle size={15} />} {toast.text}
        </div>
      )}
    </div>
  );
}