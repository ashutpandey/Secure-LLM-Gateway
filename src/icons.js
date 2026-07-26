// Icon barrel — the ONLY place that imports from lucide-react.
//
// Every component imports its icons from here, never from "lucide-react"
// directly. That keeps the icon set consistent (one source of truth) and means
// swapping to a different set — or a zero-dependency local SVG module — is a
// single-file change that touches no component.
//
// Convention: render at size 14–16 with strokeWidth ~1.75 and color
// "currentColor" so icons inherit the surrounding text color in both themes.

export {
  // status / security
  Shield,
  ShieldAlert,
  ShieldCheck,
  Lock,
  AlertTriangle,
  Ban,
  Eye,
  EyeOff,
  Bug,
  // outcomes
  Check,
  X,
  CircleCheck,
  CircleX,
  Circle,
  Info,
  // flow / gateway
  RefreshCw,
  GitBranch,
  GitCompare,
  ArrowRightLeft,
  Zap,
  // metrics
  Activity,
  Gauge,
  Clock,
  Timer,
  ListChecks,
  Target,
  BarChart3,
  // chat / actions
  Send,
  Plus,
  Search,
  Copy,
  Trash2,
  MessageSquare,
  FlaskConical,
  Sparkles,
  FileText,
  ScrollText,
  KeyRound,
  CreditCard,
  Hash,
  SlidersHorizontal,
  // layout / chrome
  Settings,
  Sun,
  Moon,
  ChevronRight,
  ChevronDown,
  PanelRight,
  PanelLeftClose,
  PanelLeftOpen,
  Cpu,
  Wifi,
} from "lucide-react";
