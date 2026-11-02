export async function shareCompanyCode(company, code, browser = navigator) {
  const text = `${company} employee verification code: ${code}\nUse this code on the employee signup page. Share only with employees of ${company}.`;
  if (typeof browser.share === 'function') {
    try {
      await browser.share({title: `${company} employee access`, text});
      return 'shared';
    } catch (error) {
      if (error.name === 'AbortError') return 'cancelled';
      throw error;
    }
  }
  await browser.clipboard.writeText(text);
  return 'copied';
}
