import sys

path = 'frontend/src/components/UnifiedReviewDashboard.jsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Current L3 metrics block:
# Total, Received, Pending, Verified, Rejected
old_l3_metrics = """    metrics: [
      {
        key: 'total',
        title: 'Total',
        icon: '👥',
        filterKey: 'total',
        className: 'total',
        getCount: (s) => (s ? s.total : '—'),
        description: 'All candidates registered across CPASS training centres',
      },
      {
        key: 'l3_received',
        title: 'Received',
        icon: '📥',
        filterKey: 'l3_received',
        className: 'received',
        getCount: (s) => (s ? (s.l3_received ?? s.cops_received ?? 0) : '—'),
        description: 'Candidates recommended by Center Head and received for COPS audit',
      },
      {
        key: 'l3_pending',
        title: 'Pending',
        icon: '⏱',
        filterKey: 'l3_pending',
        className: 'pending',
        getCount: (s) => (s ? (s.l3_pending ?? s.cops_pending ?? 0) : '—'),
        description: 'Received candidates awaiting COPS verification & endorsement',
      },
      {
        key: 'l3_verified',
        title: 'Verified',
        icon: '🛡️',
        filterKey: 'l3_verified',
        className: 'verified',
        getCount: (s) => (s ? (s.l3_verified ?? s.cops_verified ?? 0) : '—'),
        description: 'Candidates verified & endorsed by COPS team and forwarded to BL',
      },
      {
        key: 'l3_rejected_returned',
        title: 'Rejected',
        icon: '✕',
        filterKey: 'l3_rejected_returned',
        className: 'rejected',
        getCount: (s) => (s ? (s.l3_rejected_returned ?? s.cops_rejected_returned ?? 0) : '—'),
        description: 'Candidates rejected by COPS or returned to L1 coordinator',
      },
    ],"""

# New L3 metrics block:
# Total, Received, Verified, Rejected, Pending
new_l3_metrics = """    metrics: [
      {
        key: 'total',
        title: 'Total',
        icon: '👥',
        filterKey: 'total',
        className: 'total',
        getCount: (s) => (s ? s.total : '—'),
        description: 'All candidates registered across CPASS training centres',
      },
      {
        key: 'l3_received',
        title: 'Received',
        icon: '📥',
        filterKey: 'l3_received',
        className: 'received',
        getCount: (s) => (s ? (s.l3_received ?? s.cops_received ?? 0) : '—'),
        description: 'Candidates recommended by Center Head and received for COPS audit',
      },
      {
        key: 'l3_verified',
        title: 'Verified',
        icon: '🛡️',
        filterKey: 'l3_verified',
        className: 'verified',
        getCount: (s) => (s ? (s.l3_verified ?? s.cops_verified ?? 0) : '—'),
        description: 'Candidates verified & endorsed by COPS team and forwarded to BL',
      },
      {
        key: 'l3_rejected_returned',
        title: 'Rejected',
        icon: '✕',
        filterKey: 'l3_rejected_returned',
        className: 'rejected',
        getCount: (s) => (s ? (s.l3_rejected_returned ?? s.cops_rejected_returned ?? 0) : '—'),
        description: 'Candidates rejected by COPS or returned to L1 coordinator',
      },
      {
        key: 'l3_pending',
        title: 'Pending',
        icon: '⏱',
        filterKey: 'l3_pending',
        className: 'pending',
        getCount: (s) => (s ? (s.l3_pending ?? s.cops_pending ?? 0) : '—'),
        description: 'Received candidates awaiting COPS verification & endorsement',
      },
    ],"""

# Current L4 metrics block:
# Total, Received, Pending, BL Approved, Rejected
old_l4_metrics = """    metrics: [
      {
        key: 'total',
        title: 'Total',
        icon: '👥',
        filterKey: 'total',
        className: 'total',
        getCount: (s) => (s ? s.total : '—'),
        description: 'All candidates registered across your assigned regional states',
      },
      {
        key: 'l4_received',
        title: 'Received',
        icon: '📥',
        filterKey: 'l4_received',
        className: 'received',
        getCount: (s) => (s ? (s.l4_received ?? s.bl_received ?? 0) : '—'),
        description: 'Candidates verified by COPS and received for Business Leader approval',
      },
      {
        key: 'l4_pending',
        title: 'Pending',
        icon: '⏱',
        filterKey: 'l4_pending',
        className: 'pending',
        getCount: (s) => (s ? (s.l4_pending ?? s.bl_pending ?? 0) : '—'),
        description: 'Candidates awaiting Business Leader review and approval',
      },
      {
        key: 'l4_approved',
        title: 'BL Approved',
        icon: '🏆',
        filterKey: 'l4_approved',
        className: 'approved',
        getCount: (s) => (s ? (s.l4_approved ?? s.bl_approved ?? 0) : '—'),
        description: 'Candidates approved by Business Leader and forwarded for CEO sanction',
      },
      {
        key: 'l4_rejected_returned',
        title: 'Rejected',
        icon: '✕',
        filterKey: 'l4_rejected_returned',
        className: 'rejected',
        getCount: (s) => (s ? (s.l4_rejected_returned ?? s.bl_rejected_returned ?? 0) : '—'),
        description: 'Candidates rejected by BL or returned to earlier levels (L1/L2/L3)',
      },
    ],"""

# New L4 metrics block:
# Total, Received, BL Approved, Rejected, Pending
new_l4_metrics = """    metrics: [
      {
        key: 'total',
        title: 'Total',
        icon: '👥',
        filterKey: 'total',
        className: 'total',
        getCount: (s) => (s ? s.total : '—'),
        description: 'All candidates registered across your assigned regional states',
      },
      {
        key: 'l4_received',
        title: 'Received',
        icon: '📥',
        filterKey: 'l4_received',
        className: 'received',
        getCount: (s) => (s ? (s.l4_received ?? s.bl_received ?? 0) : '—'),
        description: 'Candidates verified by COPS and received for Business Leader approval',
      },
      {
        key: 'l4_approved',
        title: 'BL Approved',
        icon: '🏆',
        filterKey: 'l4_approved',
        className: 'approved',
        getCount: (s) => (s ? (s.l4_approved ?? s.bl_approved ?? 0) : '—'),
        description: 'Candidates approved by Business Leader and forwarded for CEO sanction',
      },
      {
        key: 'l4_rejected_returned',
        title: 'Rejected',
        icon: '✕',
        filterKey: 'l4_rejected_returned',
        className: 'rejected',
        getCount: (s) => (s ? (s.l4_rejected_returned ?? s.bl_rejected_returned ?? 0) : '—'),
        description: 'Candidates rejected by BL or returned to earlier levels (L1/L2/L3)',
      },
      {
        key: 'l4_pending',
        title: 'Pending',
        icon: '⏱',
        filterKey: 'l4_pending',
        className: 'pending',
        getCount: (s) => (s ? (s.l4_pending ?? s.bl_pending ?? 0) : '—'),
        description: 'Candidates awaiting Business Leader review and approval',
      },
    ],"""

# Current L5 metrics block:
# Total, Received, Pending, Sanctioned, Rejected
old_l5_metrics = """    metrics: [
      {
        key: 'total',
        title: 'Total',
        icon: '👥',
        filterKey: 'total',
        className: 'total',
        getCount: (s) => (s ? s.total : '—'),
        description: 'All candidates registered across all 12 CPASS states nationwide',
      },
      {
        key: 'l5_received',
        title: 'Received',
        icon: '📥',
        filterKey: 'l5_received',
        className: 'received',
        getCount: (s) => (s ? (s.l5_received ?? s.ceo_received ?? 0) : '—'),
        description: 'Candidates approved by Business Leaders awaiting final executive sanction',
      },
      {
        key: 'l5_pending',
        title: 'Pending',
        icon: '⏱',
        filterKey: 'l5_pending',
        className: 'pending',
        getCount: (s) => (s ? (s.l5_pending ?? s.ceo_pending ?? 0) : '—'),
        description: 'Candidates awaiting CEO executive sanction and final approval',
      },
      {
        key: 'l5_approved',
        title: 'Sanctioned',
        icon: '👑',
        filterKey: 'l5_approved',
        className: 'approved',
        getCount: (s) => (s ? (s.l5_approved ?? s.ceo_approved ?? 0) : '—'),
        description: 'Candidates finally sanctioned and approved by CEO. Workflow complete.',
      },
      {
        key: 'l5_rejected_returned',
        title: 'Rejected',
        icon: '✕',
        filterKey: 'l5_rejected_returned',
        className: 'rejected',
        getCount: (s) => (s ? (s.l5_rejected_returned ?? s.ceo_rejected_returned ?? 0) : '—'),
        description: 'Candidates rejected by CEO or returned to previous levels (L1/L2/L3/L4)',
      },
    ],"""

# New L5 metrics block:
# Total, Received, Sanctioned, Rejected, Pending
new_l5_metrics = """    metrics: [
      {
        key: 'total',
        title: 'Total',
        icon: '👥',
        filterKey: 'total',
        className: 'total',
        getCount: (s) => (s ? s.total : '—'),
        description: 'All candidates registered across all 12 CPASS states nationwide',
      },
      {
        key: 'l5_received',
        title: 'Received',
        icon: '📥',
        filterKey: 'l5_received',
        className: 'received',
        getCount: (s) => (s ? (s.l5_received ?? s.ceo_received ?? 0) : '—'),
        description: 'Candidates approved by Business Leaders awaiting final executive sanction',
      },
      {
        key: 'l5_approved',
        title: 'Sanctioned',
        icon: '👑',
        filterKey: 'l5_approved',
        className: 'approved',
        getCount: (s) => (s ? (s.l5_approved ?? s.ceo_approved ?? 0) : '—'),
        description: 'Candidates finally sanctioned and approved by CEO. Workflow complete.',
      },
      {
        key: 'l5_rejected_returned',
        title: 'Rejected',
        icon: '✕',
        filterKey: 'l5_rejected_returned',
        className: 'rejected',
        getCount: (s) => (s ? (s.l5_rejected_returned ?? s.ceo_rejected_returned ?? 0) : '—'),
        description: 'Candidates rejected by CEO or returned to previous levels (L1/L2/L3/L4)',
      },
      {
        key: 'l5_pending',
        title: 'Pending',
        icon: '⏱',
        filterKey: 'l5_pending',
        className: 'pending',
        getCount: (s) => (s ? (s.l5_pending ?? s.ceo_pending ?? 0) : '—'),
        description: 'Candidates awaiting CEO executive sanction and final approval',
      },
    ],"""

# Helper to replace with both LF and CRLF support
def replace_block(c, old_b, new_b, label):
    old_crlf = old_b.replace('\n', '\r\n')
    new_crlf = new_b.replace('\n', '\r\n')
    if old_crlf in c:
        c = c.replace(old_crlf, new_crlf)
        print(f"Replaced {label} (CRLF)")
    elif old_b in c:
        c = c.replace(old_b, new_b)
        print(f"Replaced {label} (LF)")
    else:
        print(f"FAILED to find {label}")
        sys.exit(1)
    return c

content = replace_block(content, old_l3_metrics, new_l3_metrics, "L3 Metrics")
content = replace_block(content, old_l4_metrics, new_l4_metrics, "L4 Metrics")
content = replace_block(content, old_l5_metrics, new_l5_metrics, "L5 Metrics")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("UnifiedReviewDashboard.jsx updated successfully!")

