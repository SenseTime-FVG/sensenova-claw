'use client';

import { useState, useEffect, useRef } from 'react';
import { authFetch, API_BASE } from '@/lib/authFetch';

interface SkillItem {
  name: string;
  description: string;
}

interface SlashCommandMenuProps {
  inputValue: string;
  onSelect: (skillName: string) => void;
  visible: boolean;
}

export function SlashCommandMenu({ inputValue, onSelect, visible }: SlashCommandMenuProps) {
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const menuRef = useRef<HTMLDivElement>(null);

  // 加载已启用的 skills
  useEffect(() => {
    authFetch(`${API_BASE}/api/skills`)
      .then(r => r.json())
      .then((data: any[]) => {
        setSkills(
          data
            .filter(s => s.enabled)
            .map(s => ({ name: s.name, description: s.description }))
        );
      })
      .catch(() => setSkills([]));
  }, []);

  // 过滤
  const query = inputValue.startsWith('/') ? inputValue.slice(1).toLowerCase() : '';
  const filtered = skills.filter(s =>
    s.name.toLowerCase().includes(query) || s.description.toLowerCase().includes(query)
  );

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
  const showMenu = inputValue.startsWith('/') && !inputValue.includes(' ');

  const handleSelect = (skillName: string) => {
    setInputValue(`/${skillName} `);
  };

  const handleSubmit = (text: string): boolean => {
    // 检查是否是斜杠命令
    if (text.startsWith('/')) {
      const parts = text.slice(1).split(/\s+/, 2);
      const skillName = parts[0];
      const args = text.slice(1 + skillName.length).trim();
      if (skillName) {
        onInvoke(skillName, args);
        return true; // 已处理
      }
    }
    return false; // 非斜杠命令，走正常消息发送
  };

  return { showMenu, handleSelect, handleSubmit };
}
