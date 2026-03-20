import { createBrowserRouter } from "react-router";
import WorkbenchPage from "./pages/WorkbenchPage";
import ChatPage from "./pages/ChatPage";
import ResearchPage from "./pages/ResearchPage";
import PPTPage from "./pages/PPTPage";
import AutomationPage from "./pages/AutomationPage";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: WorkbenchPage,
  },
  {
    path: "/chat",
    Component: ChatPage,
  },
  {
    path: "/research",
    Component: ResearchPage,
  },
  {
    path: "/ppt",
    Component: PPTPage,
  },
  {
    path: "/automation",
    Component: AutomationPage,
  },
]);