/**
 * School email digest for the morning paper.
 *
 * School Google accounts often block outside apps from reading Gmail, but an
 * Apps Script you write yourself runs inside your own account. Each morning
 * this emails the last day's school mail, as JSON, to your personal Gmail,
 * where the newspaper picks it up.
 *
 * Setup (signed in to your SCHOOL account):
 *   1. Go to https://script.google.com and click New project.
 *   2. Replace everything in the editor with this file. Set PERSONAL_EMAIL below.
 *   3. Pick `setup` in the function menu and click Run. Approve the permissions.
 *   4. Pick `sendDigest` and click Run once to test. Check your personal inbox.
 */

const PERSONAL_EMAIL = 'you@gmail.com';            // where the digest goes
const SUBJECT = 'Olivia Times school digest';      // must match config.toml
const SEARCH = 'newer_than:1d -category:promotions -category:social';

function sendDigest() {
  const threads = GmailApp.search(SEARCH, 0, 40);
  const items = threads.map(function (thread) {
    const msg = thread.getMessages().pop();
    return {
      from: msg.getFrom(),
      subject: msg.getSubject(),
      date: msg.getDate().toISOString(),
      important: thread.isImportant(),
      body: msg.getPlainBody().replace(/\s+/g, ' ').slice(0, 1200),
    };
  });
  const day = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
  MailApp.sendEmail(PERSONAL_EMAIL, SUBJECT + ' ' + day, JSON.stringify(items));
}

/** Run once: sends the digest every day between 5 and 6 a.m., before the paper is built. */
function setup() {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('sendDigest').timeBased().everyDays(1).atHour(5).create();
}
