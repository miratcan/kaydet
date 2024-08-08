import { render } from 'preact';
import { LocationProvider, Router, Route } from 'preact-iso';

import { Home } from './pages/Home/index.jsx';
import { NotFound } from './pages/_404.jsx';
import './style.css';

export function App() {
	return (
		<LocationProvider>
			<header>
        <h1>Zihinbaz</h1>
      </header>
      <Router>
        <Route path="/" component={Home} />
        <Route default component={NotFound} />
      </Router>
		</LocationProvider>
	);
}

render(<App />, document.getElementById('app'));
