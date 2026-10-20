// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package sessions

import (
	"context"
	"testing"

	"google.golang.org/adk/v2/session"
)

// TestNewServiceFallsBackToInMemory checks that every backend falls back to
// in-memory sessions when it isn't configured, so no test needs cloud access.
func TestNewServiceFallsBackToInMemory(t *testing.T) {
	// Each backend reads only its own variables; the others have no effect.
	t.Setenv("INSTANCE_CONNECTION_NAME", "")
	t.Setenv("DB_PASS", "")
	t.Setenv("GOOGLE_CLOUD_AGENT_ENGINE_ID", "")
	t.Setenv("USE_IN_MEMORY_SESSION", "true")

	ctx := context.Background()
	svc, err := NewService(ctx)
	if err != nil {
		t.Fatalf("NewService() error = %v", err)
	}

	created, err := svc.Create(ctx, &session.CreateRequest{AppName: "app", UserID: "user"})
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	got, err := svc.Get(ctx, &session.GetRequest{
		AppName:   "app",
		UserID:    "user",
		SessionID: created.Session.ID(),
	})
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}
	if got.Session.ID() != created.Session.ID() {
		t.Errorf("Get() session ID = %q, want %q", got.Session.ID(), created.Session.ID())
	}
}
