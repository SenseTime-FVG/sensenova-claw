'use client';

import { useState, useEffect, useRef } from 'react';
import { authFetch, API_BASE } from '@/lib/authFetch';
import {
  filterSlashCommandSkills,
  getSlashCommandQuery,
  resolveSlashCommandSubmission,
  type SlashCommandSkillItem,
} from './slashCommand';

interface SlashCommandMenuProps {
  inputValue: string;
  skills: SlashCommandSkillItem[];
  onSelect: (skillName: string) => void;
  visible: boolean;
}

export function SlashCommandMenu({ inputValue, skills, onSelect, visible }: SlashCommandMenuProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const menuRef = useRef<HTMLDivElement>(null);

  // 过滤
  const query = getSlashCommandQuery(inputValue);
  const filtered = filterSlashCommandSkills(inputValue, skills);

  // 重置选中
  useEffect(() => { setSelectedIndex(0); }, [query]);

  if (!visible || filtered.length === 0) return null;

  return (
    <div
      ref={menuRef}
      className="absolute bottom-full left-0 mb-1 w-80 max-h-48 overflow-auto bg-popover border border-border rounded-md shadow-md z-50 text-popover-foreground"
    >
      {filtered.map((skill, i) => (
        <div
          key={skill.name}
          className={`px-3 py-2 cursor-pointer ${
            i === selectedIndex ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'
          }`}
          onClick={() => onSelect(skill.name)}
          onMouseEnter={() => setSelectedIndex(i)}
        >
          <div className="text-sm font-medium">/{skill.name}</div>
          <div className="text-xs opacity-70 truncate">{skill.description}</div>
        </div>
      ))}
    </div>
  );
}

/**
 * Hook: 在聊天输入框中使用斜杠命令
 * 返回 { showMenu, handleSelect, handleSubmit }
 */
export function useSlashCommand(
  inputValue: string,
  setInputValue: (v: string) => void,
  onInvoke: (skillName: string, args: string) => void,
) {
  const [skills, setSkills] = useState<SlashCommandSkillItem[]>([]);

  useEffect(() => {
    authFetch(`${API_BASE}/api/skills`)
      .then(r => r.json())
      .then((data: Array<{ name?: string; description?: string; enabled?: boolean }>) => {
        setSkills(
          data
            .filter((skill) => skill.enabled)
            .map((skill) => ({
              name: String(skill.name || ''),
              description: String(skill.description || ''),
            }))
            .filter((skill) => skill.name),
        );
      })
      .catch(() => setSkills([]));
  }, []);

  const showMenu = inputValue.startsWith('/') && !inputValue.includes(' ');

  const handleSelect = (skillName: string) => {
    setInputValue(`/${skillName} `);
  };

  const handleSubmit = (text: string): boolean => {
    const submission = resolveSlashCommandSubmission(
      text,
      skills.map((skill) => skill.name),
    );
    if (submission.handled && submission.skillName) {
      onInvoke(submission.skillName, submission.args);
      return true;
    }
    return false;
  };

  return { showMenu, skills, handleSelect, handleSubmit };
}
