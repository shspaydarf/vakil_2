# -*- coding: utf-8 -*-
"""V153 — Claim ↔ Evidence Matrix.

Local-first evidence mapping built on V152 issues and current case documents.
It does not decide admissibility, truth, credibility, or legal sufficiency.
Every claim/evidence link keeps document-level and text-span provenance.
"""
from __future__ import annotations

from .text_utils import clean_whitespace as _clean
from .text_utils import normalize_persian_text as _norm
import re
from typing import Any, Dict, List, Tuple
from .db import get_case, get_case_documents
from .issue_engine import build_case_issues
from .source_quality import source_segment_ok

STOP = set("و در به از که را با برای این آن است هست بود شد شده می شود یک یا اما اگر تا نیز بر مورد درباره توسط علیه بین خود خودِ های ها آنچه هر همه هیچ فقط هم همچنین سپس زیرا چون ولی اما ادعا ادعای مدعی گفته گفتند حسب اظهارات".split())






def _tokens(text: str) -> List[str]:
    words = re.findall(r"[\wآ-ی]+", _norm(text))
    return [w for w in words if len(w) >= 3 and w not in STOP]

def _text_fingerprint(text: str) -> str:
    return " ".join(_tokens(text))


def _pages_with_spans(text: str) -> List[Tuple[Any, str, int, int]]:
    ms = list(re.finditer(r"\[صفحه\s+(\d+)\]", text or ""))
    if not ms:
        return [(None, text or "", 0, len(text or ""))]
    out=[]
    for i,m in enumerate(ms):
        end = ms[i+1].start() if i+1 < len(ms) else len(text)
        body = text[m.end():end]
        if body.strip(): out.append((int(m.group(1)), body, m.end(), end))
    return out


def _sentence_spans(body: str, base: int) -> List[Tuple[str,int,int]]:
    out=[]
    # Keep offsets against the original extracted document.
    for m in re.finditer(r"[^\r\n؟.!؛]+(?:[؟.!؛]|$)", body):
        raw=m.group(0); txt=_clean(raw)
        if len(txt) < 12 or not source_segment_ok(txt, min_chars=12): continue
        left=m.start(); right=m.end()
        # trim whitespace while retaining source coordinates
        lead=len(raw)-len(raw.lstrip()); trail=len(raw)-len(raw.rstrip())
        out.append((txt, base+left+lead, base+right-trail))
    return out


def _doc_sentences(doc: Dict[str,Any]) -> List[Dict[str,Any]]:
    text=doc.get('extracted_text') or ''
    out=[]
    for page,body,start,end in _pages_with_spans(text):
        for sentence, a, b in _sentence_spans(body,start):
            out.append({'document_id':doc.get('id'),'document_name':doc.get('file_name') or doc.get('name'),'page':page,'text':sentence,'char_start':a,'char_end':b})
    return out


def _score(claim: str, evidence: str) -> float:
    a=set(_tokens(claim)); b=set(_tokens(evidence))
    if not a or not b: return 0.0
    overlap=len(a & b)/max(1,len(a))
    # A high overlap made generic repeated legal wording look like evidence.
    # Require at least two meaningful shared tokens when the claim is longer.
    if len(a) >= 5 and len(a & b) < 2: return 0.0
    return round(overlap,3)


def _near_duplicate(claim: str, evidence: str) -> bool:
    """Detect copied/repeated source text masquerading as independent evidence."""
    a=set(_tokens(claim)); b=set(_tokens(evidence))
    if not a or not b: return False
    j=len(a & b)/max(1,len(a | b))
    # A near-identical sentence on another page/document is still the same
    # textual assertion and must not become independent corroboration.
    return len(a) >= 5 and j >= 0.88


def _stance(text: str) -> str:
    n=_norm(text)
    if re.search(r"(انکار|منکر|عدم\s+(?:پرداخت|انجام|تحویل|ابلاغ)|نشد(?:ه)?|نکرد(?:ه)?|رد\s+(?:شد|می‌کند|کرد)|مخالف|در حالی که|خلاف)",n):
        return 'contrary_signal'
    if re.search(r"(مدعی|ادعا|به ادعای|حسب اظهارات|اظهارات)",n):
        return 'party_assertion'
    return 'source_signal'


def _link_type(claim: str, evidence: Dict[str,Any], expected: str, *, origin: bool=False) -> str:
    """Classify the relation without treating an assertion as proof.

    An originating party statement is provenance for the claim, not independent
    support. This distinction prevents V153 from calling a claim "supported"
    merely because the same sentence that made the claim was found again.
    """
    if origin:
        return 'origin'
    s=evidence.get('stance')
    if s == 'party_assertion':
        return 'asserts'
    # Polarity is relative to the originating claim. A positive claim is
    # supported by a neutral/source statement and contradicted by an explicit
    # denial; a denial claim has the inverse relation.
    if expected == 'contrary_signal':
        return 'supports' if s == 'contrary_signal' else 'contradicts'
    if s == 'contrary_signal':
        return 'contradicts'
    return 'supports'


def _claim_key(issue: Dict[str,Any], signal: Dict[str,Any]) -> str:
    return f"{issue.get('issue_id')}|{_norm(signal.get('text'))[:180]}"


def build_evidence_matrix(uid: int, cid: int) -> Dict[str,Any]:
    case=get_case(uid,int(cid))
    if not case:
        return {'version':153,'case_id':int(cid),'claims':[],'matrix':[],'api_used':False,'error':'case_not_found'}
    issue_map=build_case_issues(uid,int(cid))
    docs=get_case_documents(uid,int(cid))
    spans=[]
    for d in docs: spans.extend(_doc_sentences(d))

    claims=[]; matrix=[]; seen=set()
    docs_by_id = {d.get('id'): d for d in docs if d.get('id') is not None}
    for issue in issue_map.get('issues') or []:
        signals=(issue.get('supporting_signals') or []) + (issue.get('contrary_signals') or [])
        for sig in signals:
            text=_clean(sig.get('text'))
            if len(text)<12: continue
            key=_claim_key(issue,sig)
            if key in seen: continue
            seen.add(key)
            cid_key=f"clm-{len(claims)+1:04d}"
            origin_doc = sig.get('document_id')
            origin_page = sig.get('page')
            origin_meta = docs_by_id.get(origin_doc, {})
            claim={'claim_id':cid_key,'issue_id':issue.get('issue_id'),'issue_label':issue.get('label'),'claim_text':text,'claim_status':'unverified','source_signal_stance':sig.get('stance'),'review_decision':None,
                   'origin_source': {'document_id': origin_doc, 'document_name': origin_meta.get('file_name') or (f'سند #{origin_doc}' if origin_doc is not None else 'منبع نامشخص'), 'page': origin_page, 'text': text, 'origin_kind': sig.get('stance') or 'source_signal'}}
            claims.append(claim)
            ranked=[]
            origin_norm=_text_fingerprint(text)
            for sp in spans:
                if not source_segment_ok(sp.get('text',''), min_chars=20):
                    continue
                score=_score(text,sp['text'])
                if score < 0.22: continue
                # Very short/common lexical matches are review leads, not evidence.
                shared=set(_tokens(text)) & set(_tokens(sp['text']))
                if len(shared) < 2: continue
                stance=_stance(sp['text'])
                exact=(sp['document_id'] is not None and _text_fingerprint(sp['text']) == origin_norm)
                ranked.append((1 if exact else 0, score, sp, stance, exact))
            ranked.sort(key=lambda x:(x[0],x[1], -len(x[2]['text'])), reverse=True)
            selected=[]; used=set()
            for exact_rank,score,sp,stance,exact in ranked:
                fingerprint=(sp['document_id'],sp['char_start'],sp['char_end'])
                if fingerprint in used: continue
                selected.append({**sp,'relevance':score,
                                 'link_type':_link_type(text,{**sp,'stance':stance},sig.get('stance'),origin=exact),
                                 'stance':stance,'origin':exact})
                used.add(fingerprint)
                if len(selected)>=6: break
            support=sum(x['link_type']=='supports' for x in selected if not x.get('origin'))
            contra=sum(x['link_type']=='contradicts' for x in selected if not x.get('origin'))
            independent_support=0
            independent_contra=0
            for x in selected:
                if x.get('origin') or x.get('link_type') not in {'supports','contradicts'}:
                    continue
                # A different page/document is a stronger provenance boundary.
                # Same-page lexical repetition remains a review signal only.
                # A different page in the same file is useful location context,
                # but is not an independent source. Independence requires a
                # distinct document record.
                different_source = (origin_doc is not None and x.get('document_id') is not None and x.get('document_id') != origin_doc)
                not_copy = not _near_duplicate(text, x.get('text',''))
                if different_source and not_copy and len(set(_tokens(text)) & set(_tokens(x.get('text','')))) >= 2:
                    if x.get('link_type') == 'supports': independent_support += 1
                    else: independent_contra += 1
            # The originating sentence itself never proves the claim. Likewise,
            # same-page repetition is not enough to call a claim supported.
            non_origin = [x for x in selected if not x.get('origin')]
            if independent_contra and independent_support: status='mixed'
            elif independent_contra: status='contradicted'
            elif independent_support: status='supported'
            elif non_origin: status='unverified'
            else: status='unsupported'
            claim['claim_status']=status
            matrix.append({'claim_id':cid_key,'issue_id':issue.get('issue_id'),'evidence':selected,
                       'support_count':support,'contradict_count':contra,
                       'evidence_gap':not bool([x for x in selected if not x.get('origin')]),
                       'independent_evidence_count':independent_support + independent_contra,
                       'independent_support_count':independent_support,
                       'independent_contradict_count':independent_contra,
                       'status_basis':'independent_source_span' if (independent_support or independent_contra) else 'no_independent_source_span'})

    # Unmapped facts become review-only evidence leads, never claims.
    leads=[]
    for x in issue_map.get('unmapped_facts') or []:
        text=_clean(x.get('text'))
        if text: leads.append({'page':x.get('page'),'text':text,'reason':'unmapped_fact_from_v152'})

    counts={
        'claims':len(claims),
        'supported':sum(c['claim_status']=='supported' for c in claims),
        'mixed':sum(c['claim_status']=='mixed' for c in claims),
        'contradicted':sum(c['claim_status']=='contradicted' for c in claims),
        'unsupported':sum(c['claim_status']=='unsupported' for c in claims),
        'unverified':sum(c['claim_status']=='unverified' for c in claims),
        'evidence_gaps':sum(m['evidence_gap'] for m in matrix),
        'unmapped_leads':len(leads),
    }
    return {
        'version':153,'case_id':int(cid),'case_name':_clean(case.get('file_name')),
        'claims':claims,'matrix':matrix,'unmapped_leads':leads,'counts':counts,
        'source_documents':len(docs),'api_used':False,
        'resolver_path':['case_db','current_case_documents','v152_issue_map','claim_extraction','source_span_index','claim_evidence_linking','support_contradiction_classification','provenance_preservation'],
        'legal_conclusion_generated':False,'legal_authorities_generated':False,
    }


def format_evidence_matrix(result: Dict[str,Any], limit: int=8) -> str:
    r=result or {}; c=r.get('counts') or {}; claims=r.get('claims') or []; by={m.get('claim_id'):m for m in r.get('matrix') or []}
    lines=['🔗 ماتریس ادعا ↔ مدرک پرونده','',f"ادعا: {c.get('claims',0)} | پشتیبانی‌شده: {c.get('supported',0)} | مختلط: {c.get('mixed',0)} | متعارض: {c.get('contradicted',0)} | بدون مدرک کافی: {c.get('unsupported',0)}",'', '⚠️ این خروجی وجود/ارتباط مدرک را نشان می‌دهد؛ اعتبار نهایی، کفایت دلیل و نتیجه حقوقی را تعیین نمی‌کند.']
    icons={'supported':'🟢','mixed':'🟠','contradicted':'🔴','unsupported':'⚪','unverified':'⚪'}
    for claim in claims[:max(1,limit)]:
        status=claim.get('claim_status','unverified'); status_label={'supported':'پشتیبانی‌شده','mixed':'مختلط','contradicted':'متعارض','unsupported':'بدون پشتوانه کافی','unverified':'تأییدنشده'}.get(status,status)
        lines += ['',f"{icons.get(status,'⚪')} {claim.get('issue_label','ادعا')} — {status_label}",f"📝 {_clean(claim.get('claim_text'))[:420]}"]
        mat=by.get(claim.get('claim_id'),{}); ev=mat.get('evidence') or []
        for e in ev[:2]:
            prefix = '↔️' if e.get('link_type')=='contradicts' else ('🗣️' if e.get('link_type') in {'origin','asserts'} else '📎')
            lines.append(f"{prefix} {e.get('document_name') or 'سند'}" + (f" — ص.{e.get('page')}" if e.get('page') else '') + f" — {_clean(e.get('text'))[:240]}")
        if mat.get('evidence_gap'): lines.append('⚠️ برای این ادعا مدرک قابل ردیابی کافی پیدا نشد.')
    if len(claims)>limit: lines.append(f"\n… {len(claims)-limit} ادعای دیگر")
    if r.get('unmapped_leads'):
        lines += ['', '🧩 سرنخ‌های بدون نگاشت از V152:']
        for x in r['unmapped_leads'][:3]: lines.append(f"• {_clean(x.get('text'))[:280]}")
    lines += ['', '🔒 مسیر: V152 Issue Map → Source Span → Evidence Matrix | API خارجی: استفاده نشد']
    return '\n'.join(lines)
