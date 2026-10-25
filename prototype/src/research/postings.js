import { money } from '../data'

// Where each bid first showed up: an email in the bid inbox, or a notice on a bid portal. These
// back the "found on" lines, so the owner can open the original and see it for himself. All of
// them are sample data, like the bids they describe.

const PORTAL_TITLES = {
  WEBS: "WEBS: Washington's Electronic Business Solution",
  FGA: 'FGA bid notice',
  'Public Purchase': 'Public Purchase bid notice',
}

const WEEKDAYS = { Wednesday: 'Wednesday, Oct 28, 2026', Thursday: 'Thursday, Oct 29, 2026', Friday: 'Friday, Oct 30, 2026' }

function email({ from, date, subject, lines, highlight }) {
  const text = [`From: ${from}`, 'To: bids@cadocary.com', `Date: ${date}`, `Subject: ${subject}`, '', ...lines].join('\n')
  return { title: subject, short: 'Email', kind: 'Email', pages: 1, from: 'Cadocary bid inbox', date, text: [text], highlight }
}

function notice({ portal, date, lines, highlight }) {
  const text = [PORTAL_TITLES[portal], 'Solicitation notice', '', ...lines].join('\n')
  return { title: `${portal} notice`, short: `${portal} notice`, kind: 'Portal record', pages: 1, from: portal, date, text: [text], highlight }
}

// The posting a bid was found in. Its `highlight` is the line the "found on" chip points at.
export function postingFor(job, postedOn) {
  const due = job.due.replace(' · ', ' at ')
  if (job.source === 'Email') {
    const subject = `${job.solicitation}: ${job.title}, request for proposals`
    return email({
      from: `${job.buyer} Purchasing`,
      date: `Sun, ${postedOn}, 2026, 9:12 PM`,
      subject,
      highlight: `Subject: ${subject}`,
      lines: [
        `${job.buyer}, ${job.agency}, is requesting proposals for: ${job.title}.`,
        '',
        `Solicitation: ${job.solicitation}`,
        `Proposals due: ${due}`,
        `Documents attached: RFP (${job.pages} pages), scope of work.`,
        '',
        'Send questions in writing to the contact named in the RFP.',
      ],
    })
  }
  const posted = `Posted: ${postedOn}, 2026`
  return notice({
    portal: job.source,
    date: postedOn,
    highlight: posted,
    lines: [
      `Solicitation number: ${job.solicitation}`,
      `Title: ${job.title}`,
      `Agency: ${job.buyer}, ${job.agency}`,
      posted,
      `Response due: ${due}`,
      `Estimated value: ${money(job.value)}`,
      'Category: Software development and IT services',
      `Documents: RFP (${job.pages} pages), Attachment A`,
    ],
  })
}

// A posting the agent left out. The highlighted line is the reason it was left out.
export function leftOutPosting(item) {
  const value = item.reason === 'Under $25,000' ? item.note : 'Not stated'
  const due = item.reason === 'Closes in under 7 days' ? WEEKDAYS[item.note.replace('due ', '')] : 'Wednesday, Dec 9, 2026'
  const lines = {
    title: `Title: ${item.title}`,
    agency: `Agency: ${item.buyer}`,
    value: `Estimated value: ${value}`,
    due: `Response due: ${due}`,
  }
  const highlight = {
    'Not software work': lines.title,
    'Under $25,000': lines.value,
    'Outside Washington': lines.agency,
    'Closes in under 7 days': lines.due,
  }[item.reason]

  if (item.source === 'Bid inbox') {
    return email({
      from: `${item.buyer} Purchasing`,
      date: 'Sun, Oct 25, 2026',
      subject: `Request for proposals: ${item.title}`,
      highlight,
      lines: [lines.agency, lines.title, lines.value, lines.due, '', 'Full documents are attached.'],
    })
  }
  return notice({ portal: item.source, date: 'Oct 25', highlight, lines: [lines.title, lines.agency, 'Posted: Oct 25, 2026', lines.due, lines.value] })
}

// The cite that opens a posting with its key line marked.
export const postingCite = (doc) => ({ src: 'posting', page: 1, section: '', quote: doc.highlight })
