import { Routes } from '@angular/router';

import { AppShellComponent } from './layout/app-shell.component';
import { LandingPage } from './pages/landing.page';
import { DiffsPage } from './pages/diffs.page';
import { DocumentsPage } from './pages/documents.page';
import { EndpointDetailPage } from './pages/endpoint-detail.page';
import { OverviewPage } from './pages/overview.page';
import { ReviewPage } from './pages/review.page';
import { RegistryPage } from './pages/registry.page';
import { ReliabilityPage } from './pages/reliability.page';
import { BenchmarkPage } from './pages/benchmark.page';
import { ObservabilityPage } from './pages/observability.page';
import { ArchitecturePage } from './pages/architecture.page';

export const routes: Routes = [
  { path: '', component: LandingPage },
  {
    path: 'app',
    component: AppShellComponent,
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'overview' },
      { path: 'overview', component: OverviewPage },
      { path: 'registry', component: RegistryPage },
      { path: 'registry/:id', component: EndpointDetailPage },
      { path: 'diffs', component: DiffsPage },
      { path: 'reliability', component: ReliabilityPage },
      { path: 'replay', redirectTo: 'reliability', pathMatch: 'full' },
      { path: 'documents', component: DocumentsPage },
      { path: 'review', component: ReviewPage },
      { path: 'benchmark', component: BenchmarkPage },
      { path: 'observability', component: ObservabilityPage },
      { path: 'architecture', component: ArchitecturePage },
    ],
  },
  { path: 'overview', redirectTo: 'app/overview', pathMatch: 'full' },
  { path: 'registry', redirectTo: 'app/registry', pathMatch: 'full' },
  { path: 'registry/:id', redirectTo: 'app/registry/:id', pathMatch: 'full' },
  { path: 'diffs', redirectTo: 'app/diffs', pathMatch: 'full' },
  { path: 'reliability', redirectTo: 'app/reliability', pathMatch: 'full' },
  { path: 'replay', redirectTo: 'app/reliability', pathMatch: 'full' },
  { path: 'documents', redirectTo: 'app/documents', pathMatch: 'full' },
  { path: 'review', redirectTo: 'app/review', pathMatch: 'full' },
  { path: 'benchmark', redirectTo: 'app/benchmark', pathMatch: 'full' },
  { path: 'observability', redirectTo: 'app/observability', pathMatch: 'full' },
  { path: 'architecture', redirectTo: 'app/architecture', pathMatch: 'full' },
  { path: '**', redirectTo: '' },
];
