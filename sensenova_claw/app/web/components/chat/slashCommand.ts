export interface SlashCommandSkillItem {
  name: string;
  description: string;
}

export interface SlashCommandSubmissionResult {
  handled: boolean;
  skillName: string | null;
  args: string;
}

export function getSlashCommandQuery(inputValue: string): string {
  return inputValue.startsWith('/') ? inputValue.slice(1).toLowerCase() : '';
}

export function filterSlashCommandSkills(
  inputValue: string,
  skills: SlashCommandSkillItem[],
): SlashCommandSkillItem[] {
  const query = getSlashCommandQuery(inputValue);
  if (!query) {
    return skills;
  }
  return skills.filter((skill) =>
    skill.name.toLowerCase().includes(query) || skill.description.toLowerCase().includes(query),
  );
}

export function resolveSlashCommandSubmission(
  text: string,
  enabledSkillNames: string[],
): SlashCommandSubmissionResult {
  if (!text.startsWith('/')) {
    return { handled: false, skillName: null, args: '' };
  }

  const parts = text.slice(1).split(/\s+/, 2);
  const rawSkillName = parts[0]?.trim() || '';
  if (!rawSkillName) {
    return { handled: false, skillName: null, args: '' };
  }

  const normalizedSkillName = rawSkillName.toLowerCase();
  const matchedSkillName = enabledSkillNames.find(
    (skillName) => skillName.toLowerCase() === normalizedSkillName,
  );
  if (!matchedSkillName) {
    return { handled: false, skillName: null, args: '' };
  }

  return {
    handled: true,
    skillName: matchedSkillName,
    args: text.slice(1 + rawSkillName.length).trim(),
  };
}
