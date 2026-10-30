import re
from collections import defaultdict
from datetime import date


def resolve(documents, query):
    as_of=query.as_of
    version=query.version
    warnings=[]
    # Only explicit temporal phrasing is inferred; arbitrary numbers are not versions.
    years=re.findall(r'\b(20\d{2})\b',query.question)
    if not as_of and not version and years and not re.search(r'\b(current|latest|today)\b',query.question,re.I):
        if len(set(years))>1:
            chosen=[]; diagnostics=[]
            for year in sorted(set(years)):
                ids,notes=resolve(documents,query.model_copy(update={'as_of':date(int(year),12,31)}))
                chosen.extend(ids);diagnostics.extend(notes)
            return list(dict.fromkeys(chosen)),list(dict.fromkeys(diagnostics))
        as_of=min(date(int(years[0]),12,31),date.today()) if int(years[0])==date.today().year else date(int(years[0]),12,31)
    if not version:
        match=re.search(r'\bversion\s+([\w.-]+)',query.question,re.I)
        version=match.group(1).rstrip('.?') if match else None
    if not as_of and not version and re.search(r'\b(historical|previous|old|superseded)\b',query.question,re.I):
        return [], ['Historical questions require an explicit year, as_of date, or version']
    groups=defaultdict(list)
    for doc in documents:
        if query.policy_family and doc['policy_family']!=query.policy_family:
            continue
        if not doc['policy_family']:
            warnings.append(f"Policy family missing for {doc['filename']}; authority cannot be resolved")
            continue
        groups[doc['policy_family']].append(doc)
    chosen=[]
    for family,group in groups.items():
        if version:
            eligible=[d for d in group if d['version']==version and d['status']!='draft']
            if as_of:
                eligible=[d for d in eligible if d['effective_date'] and d['effective_date']<=as_of.isoformat()]
        elif as_of:
            eligible=[d for d in group if d['status']!='draft' and d['effective_date'] and d['effective_date']<=as_of.isoformat()]
            if eligible:
                latest=max(d['effective_date'] for d in eligible)
                eligible=[d for d in eligible if d['effective_date']==latest]
        else:
            eligible=[d for d in group if d['status']=='current' and not d['superseded_by'] and (not d['effective_date'] or d['effective_date']<=date.today().isoformat())]
        if len(eligible)==1:
            chosen.append(eligible[0]['id'])
        elif len(eligible)>1:
            warnings.append(f'Ambiguous authority in {family}; conflicting versions excluded')
        elif not (as_of or version):
            warnings.append(f'No effective current document in {family}')
    return chosen,warnings
