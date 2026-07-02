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
  { path: '**', redirectTo: '' },
];
