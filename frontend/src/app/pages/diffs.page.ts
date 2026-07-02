import { AsyncPipe } from '@angular/common';
import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService } from '../api.service';

@Component({
  standalone: true,
  imports: [AsyncPipe, RouterLink],
  templateUrl: './diffs.page.html',
  styleUrl: './shared.css',
})
export class DiffsPage {
  private readonly api = inject(ApiService);
  readonly diffs$ = this.api.getRecentDiffs();
}
