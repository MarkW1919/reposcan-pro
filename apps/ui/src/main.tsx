import ReactDOM from "react-dom/client";

import App from "./App";
// tokens.css must load FIRST so design-token CSS variables are
// available to every selector in styles.css and dashboard.css.
import "./tokens.css";
import "./styles.css";
import "./dashboard.css";

ReactDOM.createRoot(document.getElementById("root")!).render(<App />);
